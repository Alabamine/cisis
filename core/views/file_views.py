"""
Views для файловой системы CISIS v3.21.0

Загрузка, скачивание, удаление, замена (версионность).
Проверка доступа через PermissionChecker + file_visibility_rules.
"""

import os
import mimetypes
import shutil
from datetime import datetime

from django.conf import settings
from django.http import (
    JsonResponse, HttpResponse, FileResponse, Http404
)
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from core.models import File, FileTypeDefault, FileVisibilityRule, PersonalFolderAccess
from core.models.files import FileCategory, FileType, FileVisibility
from core.permissions import PermissionChecker
from core.views.audit import log_action


# =============================================================================
# КОНСТАНТЫ
# =============================================================================

# Максимальный размер файла (байты)
MAX_FILE_SIZE = int(getattr(settings, 'FILE_MAX_SIZE_MB', 50)) * 1024 * 1024

# Допустимые расширения
ALLOWED_EXTENSIONS = set(
    getattr(settings, 'FILE_ALLOWED_EXTENSIONS',
            'pdf,jpg,jpeg,png,gif,webp,xlsx,xls,docx,doc,csv,txt,zip,rar').split(',')
)

# Размер миниатюры
THUMBNAIL_SIZE = (200, 200)


# =============================================================================
# ПРОВЕРКА ДОСТУПА
# =============================================================================

def _get_files_column(category):
    """Возвращает имя столбца в журнале FILES для данной категории"""
    mapping = {
        FileCategory.SAMPLE: 'samples_files',
        FileCategory.CLIENT: 'clients_files',
        FileCategory.EQUIPMENT: 'equipment_files',
        FileCategory.STANDARD: 'standards_files',
        FileCategory.QMS: 'qms_files',
        FileCategory.PERSONAL: 'personal_files',
        FileCategory.INBOX: 'inbox_files',
    }
    return mapping.get(category, 'samples_files')


def _can_view_file(user, file_obj):
    """
    Проверяет, может ли пользователь видеть файл.
    Три уровня: категория → сущность → тип файла.
    """
    # 1. Доступ к категории
    column = _get_files_column(file_obj.category)
    if not PermissionChecker.can_view(user, 'FILES', column):
        return False

    # 2. Доступ к сущности (упрощённая проверка)
    # Полная проверка через _build_base_queryset слишком тяжёлая для единичного файла,
    # поэтому проверяем доступ к журналу сущности
    if file_obj.sample_id:
        if not PermissionChecker.has_journal_access(user, 'SAMPLES'):
            return False
    if file_obj.acceptance_act_id or file_obj.contract_id:
        if not PermissionChecker.can_view(user, 'CLIENTS', 'access'):
            return False

    # 3. Личные папки
    if file_obj.category == FileCategory.PERSONAL:
        if file_obj.owner_id == user.id:
            return True
        return PersonalFolderAccess.objects.filter(
            owner_id=file_obj.owner_id,
            granted_to_id=user.id
        ).exists()

    # 4. Видимость типа файла
    if file_obj.visibility == FileVisibility.RESTRICTED:
        blocked = FileVisibilityRule.objects.filter(
            file_type=file_obj.file_type,
            category=file_obj.category,
            role=user.role
        ).exists()
        if blocked:
            return False

    # 5. Приватные файлы
    if file_obj.visibility == FileVisibility.PRIVATE:
        if file_obj.uploaded_by_id != user.id and file_obj.owner_id != user.id:
            return False

    return True


def _can_edit_file(user, file_obj):
    """Может ли пользователь редактировать/удалять файл"""
    column = _get_files_column(file_obj.category)
    if not PermissionChecker.can_edit(user, 'FILES', column):
        return False

    # Для личных папок — только владелец или тот, кому дали EDIT
    if file_obj.category == FileCategory.PERSONAL:
        if file_obj.owner_id == user.id:
            return True
        return PersonalFolderAccess.objects.filter(
            owner_id=file_obj.owner_id,
            granted_to_id=user.id,
            access_level='EDIT'
        ).exists()

    return True


def _can_upload_to_category(user, category):
    """Может ли пользователь загружать файлы в категорию"""
    column = _get_files_column(category)
    return PermissionChecker.can_edit(user, 'FILES', column)


# =============================================================================
# ПОЛУЧЕНИЕ ФАЙЛОВ ДЛЯ СУЩНОСТИ
# =============================================================================

def get_files_for_entity(user, entity_type, entity_id):
    """
    Возвращает файлы, привязанные к сущности, с учётом видимости.
    Используется в карточках образцов, актов и т.д.

    entity_type: 'sample', 'acceptance_act', 'contract', 'equipment', 'standard'
    entity_id: ID сущности
    """
    filter_kwargs = {
        f'{entity_type}_id': entity_id,
        'is_deleted': False,
        'current_version': True,
    }
    files = File.objects.filter(**filter_kwargs).order_by('file_type', '-uploaded_at')

    # Фильтрация по видимости
    visible_files = []
    hidden_types = set()

    for f in files:
        if _can_view_file(user, f):
            visible_files.append(f)
        else:
            hidden_types.add(f.file_type)

    # Группировка по file_type
    grouped = {}
    for f in visible_files:
        if f.file_type not in grouped:
            grouped[f.file_type] = []
        grouped[f.file_type].append(f)

    return {
        'files': visible_files,
        'grouped': grouped,
        'hidden_types': hidden_types,
        'total_count': len(visible_files),
    }


# =============================================================================
# ЗАГРУЗКА ФАЙЛА
# =============================================================================

@login_required
@require_POST
def file_upload(request):
    """
    Загрузка файла.

    POST параметры:
    - file: файл
    - category: категория (SAMPLE, CLIENT, ...)
    - file_type: тип файла (PHOTO, PROTOCOL, ...)
    - entity_type: тип сущности (sample, acceptance_act, contract, equipment, standard)
    - entity_id: ID сущности
    - description: описание (опционально)
    """
    user = request.user

    # Параметры
    uploaded_file = request.FILES.get('file')
    category = request.POST.get('category', '')
    file_type = request.POST.get('file_type', '')
    entity_type = request.POST.get('entity_type', '')
    entity_id = request.POST.get('entity_id', '')
    description = request.POST.get('description', '')

    # Валидация: файл
    if not uploaded_file:
        return JsonResponse({'error': 'Файл не выбран'}, status=400)

    # Валидация: размер
    if uploaded_file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        return JsonResponse(
            {'error': f'Файл слишком большой (макс. {max_mb} МБ)'},
            status=400
        )

    # Валидация: расширение
    ext = os.path.splitext(uploaded_file.name)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        return JsonResponse(
            {'error': f'Недопустимый формат файла (.{ext})'},
            status=400
        )

    # Валидация: категория
    valid_categories = [c[0] for c in FileCategory.CHOICES]
    if category not in valid_categories:
        return JsonResponse({'error': 'Неверная категория'}, status=400)

    # Проверка прав на загрузку
    if not _can_upload_to_category(user, category):
        return JsonResponse({'error': 'Нет прав на загрузку в эту категорию'}, status=403)

    # Получаем сущность
    entity_obj = None
    entity_kwargs = {}

    if entity_type and entity_id:
        try:
            entity_id = int(entity_id)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Неверный ID сущности'}, status=400)

        # Импортируем модели
        from core.models import Sample, AcceptanceAct, Contract, Equipment, Standard

        model_map = {
            'sample': (Sample, 'sample'),
            'acceptance_act': (AcceptanceAct, 'acceptance_act'),
            'contract': (Contract, 'contract'),
            'equipment': (Equipment, 'equipment'),
            'standard': (Standard, 'standard'),
        }

        if entity_type in model_map:
            model_class, field_name = model_map[entity_type]
            try:
                entity_obj = model_class.objects.get(id=entity_id)
                entity_kwargs[field_name] = entity_obj
            except model_class.DoesNotExist:
                return JsonResponse({'error': 'Сущность не найдена'}, status=404)

    # Генерация пути
    path_kwargs = {}
    if entity_obj:
        path_kwargs[entity_type] = entity_obj
    if category == FileCategory.PERSONAL:
        path_kwargs['user'] = user

    relative_dir = File.get_upload_path(category, file_type, **path_kwargs)
    absolute_dir = os.path.join(settings.MEDIA_ROOT, relative_dir)

    # Создаём папки
    os.makedirs(absolute_dir, exist_ok=True)

    # Имя файла (с дедупликацией)
    safe_name = _safe_filename(uploaded_file.name)
    final_name = _unique_filename(absolute_dir, safe_name)
    relative_path = os.path.join(relative_dir, final_name)
    absolute_path = os.path.join(absolute_dir, final_name)

    # Сохраняем файл на диск
    with open(absolute_path, 'wb') as dest:
        for chunk in uploaded_file.chunks():
            dest.write(chunk)

    # MIME-тип
    mime, _ = mimetypes.guess_type(uploaded_file.name)

    # Дефолтная видимость
    visibility = File.get_default_visibility(category, file_type)

    # Создаём запись в БД
    file_record = File(
        file_path=relative_path,
        original_name=uploaded_file.name,
        file_size=uploaded_file.size,
        mime_type=mime or '',
        category=category,
        file_type=file_type,
        visibility=visibility,
        description=description,
        uploaded_by=user,
    )

    # Привязка к сущности
    if entity_type == 'sample':
        file_record.sample = entity_obj
    elif entity_type == 'acceptance_act':
        file_record.acceptance_act = entity_obj
    elif entity_type == 'contract':
        file_record.contract = entity_obj
    elif entity_type == 'equipment':
        file_record.equipment = entity_obj
    elif entity_type == 'standard':
        file_record.standard = entity_obj

    # Личная папка
    if category == FileCategory.PERSONAL:
        file_record.owner = user

    file_record.save()

    # Генерация миниатюры для изображений
    if file_record.is_image:
        _generate_thumbnail(file_record)

    # Аудит
    entity_audit_type = entity_type.upper() if entity_type else 'FILE'
    entity_audit_id = entity_id if entity_id else file_record.id
    log_action(
        request,
        entity_type=entity_audit_type,
        entity_id=entity_audit_id,
        action='FILE_UPLOAD',
        extra_data={'detail': f'Загружен файл: {uploaded_file.name} ({file_record.size_display}), тип: {file_type}'}
    )

    return JsonResponse({
        'success': True,
        'file_id': file_record.id,
        'file_name': file_record.original_name,
        'file_size': file_record.size_display,
        'file_type': file_record.file_type,
        'version': file_record.version,
    })


# =============================================================================
# СКАЧИВАНИЕ ФАЙЛА
# =============================================================================

@login_required
@require_GET
def file_download(request, file_id):
    """Скачивание файла с проверкой доступа"""
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)

    if not _can_view_file(request.user, file_obj):
        return JsonResponse({'error': 'Нет доступа к файлу'}, status=403)

    # Проверяем, что файл существует на диске
    full_path = file_obj.full_path
    if not os.path.exists(full_path):
        raise Http404('Файл не найден на диске')

    # Аудит скачивания
    log_action(
        request,
        entity_type=file_obj.entity_type.upper() if file_obj.entity_type else 'FILE',
        entity_id=file_obj.sample_id or file_obj.acceptance_act_id or file_obj.contract_id or file_obj.equipment_id or file_obj.standard_id or file_obj.id,
        action='FILE_DOWNLOAD',
        extra_data={'detail': f'Скачан файл: {file_obj.original_name}'}
    )

    # Отдаём файл
    response = FileResponse(
        open(full_path, 'rb'),
        content_type=file_obj.mime_type or 'application/octet-stream'
    )
    response['Content-Disposition'] = f'attachment; filename="{file_obj.original_name}"'
    return response


# =============================================================================
# ПРЕВЬЮ / МИНИАТЮРА
# =============================================================================

@login_required
@require_GET
def file_thumbnail(request, file_id):
    """Отдаёт миниатюру файла"""
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)

    if not _can_view_file(request.user, file_obj):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    thumb_path = file_obj.full_thumbnail_path
    if thumb_path and os.path.exists(thumb_path):
        return FileResponse(open(thumb_path, 'rb'), content_type='image/jpeg')

    # Если миниатюры нет — отдаём оригинал (для изображений) или 404
    if file_obj.is_image and os.path.exists(file_obj.full_path):
        return FileResponse(
            open(file_obj.full_path, 'rb'),
            content_type=file_obj.mime_type or 'image/jpeg'
        )

    raise Http404('Миниатюра не найдена')


# =============================================================================
# УДАЛЕНИЕ ФАЙЛА (мягкое)
# =============================================================================

@login_required
@require_POST
def file_delete(request, file_id):
    """Мягкое удаление файла"""
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)

    if not _can_edit_file(request.user, file_obj):
        return JsonResponse({'error': 'Нет прав на удаление'}, status=403)

    # Мягкое удаление
    file_obj.is_deleted = True
    file_obj.deleted_at = timezone.now()
    file_obj.deleted_by = request.user
    file_obj.save()

    # Аудит
    log_action(
        request,
        entity_type=file_obj.entity_type.upper() if file_obj.entity_type else 'FILE',
        entity_id=file_obj.sample_id or file_obj.acceptance_act_id or file_obj.contract_id or file_obj.equipment_id or file_obj.standard_id or file_obj.id,
        action='FILE_DELETE',
        extra_data={'detail': f'Удалён файл: {file_obj.original_name}'}
    )

    return JsonResponse({'success': True})


# =============================================================================
# ЗАМЕНА ФАЙЛА (версионность)
# =============================================================================

@login_required
@require_POST
def file_replace(request, file_id):
    """
    Замена файла новой версией.
    Старая версия сохраняется в _versions/.
    """
    old_file = get_object_or_404(File, id=file_id, is_deleted=False, current_version=True)

    if not _can_edit_file(request.user, old_file):
        return JsonResponse({'error': 'Нет прав на замену'}, status=403)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': 'Файл не выбран'}, status=400)

    # Валидация размера и расширения
    if uploaded_file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        return JsonResponse({'error': f'Файл слишком большой (макс. {max_mb} МБ)'}, status=400)

    ext = os.path.splitext(uploaded_file.name)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        return JsonResponse({'error': f'Недопустимый формат (.{ext})'}, status=400)

    # 1. Перемещаем старый файл в _versions/
    _move_to_versions(old_file)

    # 2. Помечаем старый как неактуальный
    old_file.current_version = False
    old_file.save()

    # 3. Сохраняем новый файл на диск (в ту же папку, что и старый)
    old_dir = os.path.dirname(os.path.join(settings.MEDIA_ROOT, old_file.file_path))
    os.makedirs(old_dir, exist_ok=True)

    safe_name = _safe_filename(uploaded_file.name)
    final_name = _unique_filename(old_dir, safe_name)
    relative_dir = os.path.dirname(old_file.file_path)
    relative_path = os.path.join(relative_dir, final_name)
    absolute_path = os.path.join(old_dir, final_name)

    with open(absolute_path, 'wb') as dest:
        for chunk in uploaded_file.chunks():
            dest.write(chunk)

    # MIME-тип
    mime, _ = mimetypes.guess_type(uploaded_file.name)

    # 4. Создаём новую запись
    new_file = File(
        file_path=relative_path,
        original_name=uploaded_file.name,
        file_size=uploaded_file.size,
        mime_type=mime or '',
        category=old_file.category,
        file_type=old_file.file_type,
        # Копируем привязки
        sample_id=old_file.sample_id,
        acceptance_act_id=old_file.acceptance_act_id,
        contract_id=old_file.contract_id,
        equipment_id=old_file.equipment_id,
        standard_id=old_file.standard_id,
        owner_id=old_file.owner_id,
        # Видимость наследуется
        visibility=old_file.visibility,
        # Версионность
        version=old_file.version + 1,
        current_version=True,
        replaces=old_file,
        # Метаданные
        description=old_file.description,
        uploaded_by=request.user,
    )
    new_file.save()

    # Миниатюра
    if new_file.is_image:
        _generate_thumbnail(new_file)

    # Аудит
    log_action(
        request,
        entity_type=new_file.entity_type.upper() if new_file.entity_type else 'FILE',
        entity_id=new_file.sample_id or new_file.acceptance_act_id or new_file.contract_id or new_file.equipment_id or new_file.standard_id or new_file.id,
        action='FILE_REPLACE',
        extra_data={'detail': f'Заменён файл: {old_file.original_name} (v{old_file.version}) → {uploaded_file.name} (v{new_file.version})'}
    )

    return JsonResponse({
        'success': True,
        'file_id': new_file.id,
        'file_name': new_file.original_name,
        'version': new_file.version,
    })


# =============================================================================
# ПОЛУЧЕНИЕ ТИПОВ ФАЙЛОВ ДЛЯ КАТЕГОРИИ (AJAX)
# =============================================================================

@login_required
@require_GET
def api_file_types(request, category):
    """Возвращает доступные типы файлов для категории (для выпадающего списка)"""
    choices = FileType.CHOICES_BY_CATEGORY.get(category, [])
    return JsonResponse({
        'types': [{'value': c[0], 'label': c[1]} for c in choices]
    })


# =============================================================================
# СПИСОК ФАЙЛОВ ДЛЯ СУЩНОСТИ (AJAX)
# =============================================================================

@login_required
@require_GET
def api_entity_files(request, entity_type, entity_id):
    """
    Возвращает файлы сущности для блока файлов в карточке.
    """
    data = get_files_for_entity(request.user, entity_type, int(entity_id))

    files_list = []
    for f in data['files']:
        files_list.append({
            'id': f.id,
            'original_name': f.original_name,
            'file_type': f.file_type,
            'file_size': f.size_display,
            'version': f.version,
            'version_count': f.version_count,
            'uploaded_by': str(f.uploaded_by) if f.uploaded_by else '',
            'uploaded_at': f.uploaded_at.strftime('%d.%m.%Y') if f.uploaded_at else '',
            'is_image': f.is_image,
            'is_pdf': f.is_pdf,
            'has_thumbnail': bool(f.thumbnail_path),
            'description': f.description,
        })

    return JsonResponse({
        'files': files_list,
        'hidden_types': list(data['hidden_types']),
        'total_count': data['total_count'],
    })


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _safe_filename(filename):
    """Убирает опасные символы из имени файла"""
    # Оставляем только безопасные символы
    name, ext = os.path.splitext(filename)
    safe = re.sub(r'[^\w\s\-\.\(\)]', '', name, flags=re.UNICODE)
    safe = safe.strip()
    return (safe or 'file') + ext.lower()


def _unique_filename(directory, filename):
    """Генерирует уникальное имя файла в папке"""
    name, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1

    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f'{name}_{counter}{ext}'
        counter += 1

    return candidate


def _move_to_versions(file_obj):
    """Перемещает файл в подпапку _versions/ с суффиксом версии"""
    full_path = file_obj.full_path
    if not os.path.exists(full_path):
        return

    directory = os.path.dirname(full_path)
    versions_dir = os.path.join(directory, '_versions')
    os.makedirs(versions_dir, exist_ok=True)

    name, ext = os.path.splitext(os.path.basename(full_path))
    date_suffix = file_obj.uploaded_at.strftime('%Y%m%d') if file_obj.uploaded_at else 'unknown'
    versioned_name = f'{name}_v{file_obj.version}_{date_suffix}{ext}'
    versioned_path = os.path.join(versions_dir, versioned_name)

    shutil.move(full_path, versioned_path)

    # Обновляем путь в записи
    rel_versions_dir = os.path.join(os.path.dirname(file_obj.file_path), '_versions')
    file_obj.file_path = os.path.join(rel_versions_dir, versioned_name)
    file_obj.save()


def _generate_thumbnail(file_obj):
    """Генерирует миниатюру для изображения"""
    try:
        from PIL import Image

        full_path = file_obj.full_path
        if not os.path.exists(full_path):
            return

        directory = os.path.dirname(full_path)
        thumbs_dir = os.path.join(directory, '.thumbnails')
        os.makedirs(thumbs_dir, exist_ok=True)

        name, _ = os.path.splitext(os.path.basename(full_path))
        thumb_name = f'{name}_thumb.jpg'
        thumb_path = os.path.join(thumbs_dir, thumb_name)

        with Image.open(full_path) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            # Конвертируем в RGB (для PNG с альфа-каналом)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(thumb_path, 'JPEG', quality=85)

        # Сохраняем путь к миниатюре
        rel_thumbs_dir = os.path.join(os.path.dirname(file_obj.file_path), '.thumbnails')
        file_obj.thumbnail_path = os.path.join(rel_thumbs_dir, thumb_name)
        file_obj.save()

    except Exception as e:
        # Если не удалось — не критично, просто нет превью
        print(f'[WARNING] Не удалось создать миниатюру для {file_obj.original_name}: {e}')


# Нужен import re в начале файла
import re