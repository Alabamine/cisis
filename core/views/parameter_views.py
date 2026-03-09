"""
CISIS v3.22.0 — Views для справочника стандартов и управления показателями.

Страницы:
  standards_list              — реестр стандартов (фильтрация, создание)
  standard_detail             — карточка стандарта (CRUD полей + показатели)

AJAX (стандарты):
  api_standard_save           — создание/редактирование стандарта
  api_standard_toggle         — активация/деактивация стандарта

AJAX (показатели):
  api_parameter_save          — создание/редактирование привязки показателя к стандарту
  api_parameter_delete        — удаление привязки показателя из стандарта
  api_parameter_search        — поиск в справочнике показателей (для комбобокса)
  api_parameter_create        — создание нового показателя в справочнике
  api_parameter_reorder       — сохранение порядка показателей
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from core.models import Laboratory, Standard
from core.models.parameters import (
    Parameter,
    ParameterCategory,
    ParameterRole,
    StandardParameter,
)
from core.permissions import PermissionChecker
from core.views.audit import log_action
from core.models.base import AccreditationArea
from django.db import connection


# ============================================================
# Проверка доступа
# ============================================================

def _check_access(user):
    """VIEW-доступ к справочнику стандартов и показателей."""
    return PermissionChecker.can_view(user, 'SAMPLES', 'parameters_management')


def _can_edit(user):
    """EDIT-доступ к справочнику стандартов и показателей."""
    return PermissionChecker.can_edit(user, 'SAMPLES', 'parameters_management')


# ============================================================
# Реестр стандартов
# ============================================================

@login_required
def standards_list(request):
    """Реестр стандартов с количеством показателей."""
    if not _check_access(request.user):
        messages.error(request, 'У вас нет доступа к справочнику стандартов.')
        return redirect('workspace_home')

    can_edit = _can_edit(request.user)

    # Фильтрация
    search_query = request.GET.get('q', '').strip()
    lab_filter = request.GET.get('lab', '').strip()
    show_inactive = request.GET.get('inactive', '') == '1'

    standards = Standard.objects.all()
    if not show_inactive:
        standards = standards.filter(is_active=True)

    standards = standards.annotate(
        params_total=Count(
            'standard_parameters',
            filter=Q(standard_parameters__is_active=True),
        ),
        params_primary=Count(
            'standard_parameters',
            filter=Q(
                standard_parameters__is_active=True,
                standard_parameters__parameter_role='PRIMARY',
            ),
        ),
        params_auxiliary=Count(
            'standard_parameters',
            filter=Q(
                standard_parameters__is_active=True,
                standard_parameters__parameter_role='AUXILIARY',
            ),
        ),
    )

    if search_query:
        standards = standards.filter(
            Q(code__icontains=search_query) | Q(name__icontains=search_query)
        )

    if lab_filter:
        standards = standards.filter(standardlaboratory__laboratory_id=lab_filter)

    standards = standards.order_by('code')

    # Лаборатории для фильтра
    laboratories = Laboratory.objects.filter(
        department_type='LAB', is_active=True
    ).order_by('code_display')
    try:
        all_areas = AccreditationArea.objects.filter(is_active=True).order_by('name')
    except Exception:
        all_areas = []
    context = {
        'standards': standards,
        'can_edit': can_edit,
        'search_query': search_query,
        'lab_filter': lab_filter,
        'show_inactive': show_inactive,
        'laboratories': laboratories,
        'total_count': standards.count(),
        'all_areas': all_areas,
    }

    return render(request, 'core/standards_parameters_list.html', context)


# ============================================================
# Карточка стандарта (поля + показатели)
# ============================================================

@login_required
def standard_detail(request, standard_id):
    """Карточка стандарта — редактирование полей + CRUD показателей."""
    if not _check_access(request.user):
        messages.error(request, 'У вас нет доступа к справочнику стандартов.')
        return redirect('workspace_home')

    standard = get_object_or_404(Standard, id=standard_id)
    can_edit = _can_edit(request.user)

    # Показатели стандарта
    std_parameters = (
        StandardParameter.objects
        .filter(standard=standard, is_active=True)
        .select_related('parameter')
        .order_by('display_order', 'parameter__name')
    )

    stats = {
        'total': std_parameters.count(),
        'primary': std_parameters.filter(parameter_role='PRIMARY').count(),
        'auxiliary': std_parameters.filter(parameter_role='AUXILIARY').count(),
        'calculated': std_parameters.filter(parameter_role='CALCULATED').count(),
        'default': std_parameters.filter(is_default=True).count(),
    }

    # Лаборатории и области аккредитации для формы стандарта
    all_laboratories = Laboratory.objects.filter(
        department_type='LAB', is_active=True
    ).order_by('code_display')

    # Текущие лаборатории стандарта (через M2M)
    standard_lab_ids = list(
        standard.standardlaboratory_set.values_list('laboratory_id', flat=True)
    )

    # Области аккредитации
    from core.models.base import AccreditationArea
    all_areas = AccreditationArea.objects.filter(is_active=True).order_by('name') if hasattr(Standard, 'accreditation_areas') else []
    standard_area_ids = []
    try:
        standard_area_ids = list(
            standard.standardaccreditationarea_set.values_list('accreditation_area_id', flat=True)
        )
    except Exception:
        pass

    # Справочные данные для форм показателей
    categories = ParameterCategory.choices
    roles = ParameterRole.choices

    # ── Допущенные сотрудники (через области аккредитации) ⭐ v3.28.0 ──
    admitted_by_area = []
    excluded_user_ids = set()
    non_default_area_ids = [a_id for a_id in standard_area_ids
                            if a_id in {a.id for a in all_areas if not a.is_default}]

    if non_default_area_ids:
        # Исключения для этого стандарта
        with connection.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM user_standard_exclusions WHERE standard_id = %s",
                [standard.id]
            )
            excluded_user_ids = {row[0] for row in cur.fetchall()}

        with connection.cursor() as cur:
            cur.execute("""
                SELECT
                    aa.id AS area_id, aa.name AS area_name,
                    u.id AS user_id, u.last_name, u.first_name, u.sur_name,
                    l.code_display AS lab_display
                FROM user_accreditation_areas uaa
                JOIN accreditation_areas aa ON aa.id = uaa.accreditation_area_id
                JOIN users u ON u.id = uaa.user_id AND u.is_active = TRUE
                LEFT JOIN laboratories l ON l.id = u.laboratory_id
                WHERE uaa.accreditation_area_id = ANY(%s)
                ORDER BY aa.name, l.code_display, u.last_name, u.first_name
            """, [non_default_area_ids])

            columns = [col[0] for col in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        # Помечаем исключённых
        for row in rows:
            row['excluded'] = row['user_id'] in excluded_user_ids

        # Группируем по области
        from itertools import groupby
        for area_name, group in groupby(rows, key=lambda r: (r['area_id'], r['area_name'])):
            users_list = list(group)
            admitted_by_area.append({
                'area_id': area_name[0],
                'area_name': area_name[1],
                'users': users_list,
                'count': len([u for u in users_list if not u['excluded']]),
                'excluded_count': len([u for u in users_list if u['excluded']]),
            })

    can_edit_exclusions = _can_edit(request.user)

    context = {
        'standard': standard,
        'std_parameters': std_parameters,
        'stats': stats,
        'can_edit': can_edit,
        'categories': categories,
        'roles': roles,
        'all_laboratories': all_laboratories,
        'standard_lab_ids': standard_lab_ids,
        'all_areas': all_areas,
        'standard_area_ids': standard_area_ids,
        'admitted_by_area': admitted_by_area,
        'can_edit_exclusions': can_edit_exclusions,
    }
    return render(request, 'core/standard_parameters_detail.html', context)


# ============================================================
# AJAX: Сохранение стандарта (создание или редактирование)
# ============================================================

@login_required
@require_POST
def api_standard_save(request):
    """
    Создание или редактирование стандарта.

    POST JSON:
      standard_id    — ID стандарта (NULL для создания)
      code           — код стандарта (обязательно)
      name           — название
      test_type      — тип испытания
      test_code      — код испытания
      laboratory_ids — массив ID лабораторий
      area_ids       — массив ID областей аккредитации
    """
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав на редактирование'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    standard_id = data.get('standard_id')
    code = data.get('code', '').strip()

    if not code:
        return JsonResponse({'error': 'Код стандарта обязателен'}, status=400)

    if standard_id:
        # Редактирование
        standard = get_object_or_404(Standard, id=standard_id)
        action = 'standard_updated'
    else:
        # Проверка уникальности кода
        if Standard.objects.filter(code=code).exists():
            return JsonResponse({'error': f'Стандарт с кодом «{code}» уже существует'}, status=400)
        standard = Standard()
        action = 'standard_created'

    standard.code = code
    standard.name = data.get('name', '').strip() or None
    standard.test_type = data.get('test_type', '').strip() or None
    standard.test_code = data.get('test_code', '').strip() or None
    standard.save()

    # M2M: лаборатории
    lab_ids = data.get('laboratory_ids', [])
    if lab_ids is not None:
        from core.models.base import StandardLaboratory
        StandardLaboratory.objects.filter(standard=standard).delete()
        for lab_id in lab_ids:
            try:
                StandardLaboratory.objects.create(
                    standard=standard,
                    laboratory_id=int(lab_id),
                )
            except Exception:
                pass

    # M2M: области аккредитации
    area_ids = data.get('area_ids', [])
    if area_ids is not None:
        try:
            from core.models.base import StandardAccreditationArea
            StandardAccreditationArea.objects.filter(standard=standard).delete()
            for area_id in area_ids:
                try:
                    StandardAccreditationArea.objects.create(
                        standard=standard,
                        accreditation_area_id=int(area_id),
                    )
                except Exception:
                    pass
        except ImportError:
            pass

    log_action(
        request,
        entity_type='standard',
        entity_id=standard.id,
        action=action,
        extra_data={'code': standard.code, 'name': standard.name},
    )

    return JsonResponse({
        'success': True,
        'standard_id': standard.id,
        'code': standard.code,
        'redirect_url': f'/workspace/standards/{standard.id}/',
    })


# ============================================================
# AJAX: Активация/деактивация стандарта
# ============================================================

@login_required
@require_POST
def api_standard_toggle(request):
    """Переключение is_active стандарта."""
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    standard_id = data.get('standard_id')
    if not standard_id:
        return JsonResponse({'error': 'standard_id обязателен'}, status=400)

    standard = get_object_or_404(Standard, id=standard_id)
    standard.is_active = not standard.is_active
    standard.save(update_fields=['is_active'])

    log_action(
        request,
        entity_type='standard',
        entity_id=standard.id,
        action='standard_activated' if standard.is_active else 'standard_deactivated',
        extra_data={'code': standard.code},
    )

    return JsonResponse({
        'success': True,
        'is_active': standard.is_active,
        'message': f'Стандарт {"активирован" if standard.is_active else "деактивирован"}',
    })


# ============================================================
# AJAX: Сохранение привязки показателя к стандарту
# ============================================================

@login_required
@require_POST
def api_parameter_save(request):
    """Создание или редактирование привязки показателя к стандарту."""
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав на редактирование'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    standard_id = data.get('standard_id')
    std_parameter_id = data.get('std_parameter_id')
    parameter_id = data.get('parameter_id')

    if not standard_id or not parameter_id:
        return JsonResponse({'error': 'standard_id и parameter_id обязательны'}, status=400)

    standard = get_object_or_404(Standard, id=standard_id)
    parameter = get_object_or_404(Parameter, id=parameter_id)

    role = data.get('parameter_role', 'PRIMARY')
    if role not in [r[0] for r in ParameterRole.choices]:
        return JsonResponse({'error': f'Некорректная роль: {role}'}, status=400)

    if std_parameter_id:
        sp = get_object_or_404(StandardParameter, id=std_parameter_id, standard=standard)
        action = 'parameter_updated'
    else:
        if StandardParameter.objects.filter(
            standard=standard, parameter=parameter, is_active=True
        ).exists():
            return JsonResponse(
                {'error': f'Показатель «{parameter.name}» уже привязан к этому стандарту'},
                status=400,
            )
        sp = StandardParameter(standard=standard)
        action = 'parameter_added'

    sp.parameter = parameter
    sp.parameter_role = role
    sp.is_default = data.get('is_default', True)
    sp.unit_override = data.get('unit_override', '').strip() or None
    sp.precision = data.get('precision') if data.get('precision') not in (None, '', 'null') else None
    sp.report_order = data.get('report_order', 0) or 0
    sp.display_order = data.get('display_order', 0) or 0
    sp.is_active = True
    sp.save()

    log_action(
        request,
        entity_type='standard',
        entity_id=standard.id,
        action=action,
        extra_data={
            'parameter_id': parameter.id,
            'parameter_name': parameter.name,
            'role': role,
            'std_parameter_id': sp.id,
        },
    )

    return JsonResponse({
        'success': True,
        'std_parameter_id': sp.id,
        'parameter_id': parameter.id,
        'parameter_name': parameter.name,
        'unit': sp.effective_unit,
        'role': sp.parameter_role,
        'role_display': sp.get_parameter_role_display(),
        'is_default': sp.is_default,
    })


# ============================================================
# AJAX: Удаление привязки показателя
# ============================================================

@login_required
@require_POST
def api_parameter_delete(request):
    """Мягкое удаление привязки показателя к стандарту."""
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав на удаление'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    std_parameter_id = data.get('std_parameter_id')
    if not std_parameter_id:
        return JsonResponse({'error': 'std_parameter_id обязателен'}, status=400)

    sp = get_object_or_404(StandardParameter, id=std_parameter_id)

    from core.models.parameters import SampleParameter
    usage_count = SampleParameter.objects.filter(standard_parameter=sp).count()

    sp.is_active = False
    sp.save(update_fields=['is_active', 'updated_at'])

    log_action(
        request,
        entity_type='standard',
        entity_id=sp.standard_id,
        action='parameter_removed',
        extra_data={
            'parameter_id': sp.parameter_id,
            'parameter_name': sp.parameter.name,
            'std_parameter_id': sp.id,
            'usage_count': usage_count,
        },
    )

    return JsonResponse({
        'success': True,
        'usage_count': usage_count,
        'message': (
            f'Показатель удалён. Используется в {usage_count} образцах.'
            if usage_count > 0
            else 'Показатель удалён.'
        ),
    })


# ============================================================
# AJAX: Поиск показателей в справочнике
# ============================================================

@login_required
@require_GET
def api_parameter_search(request):
    """Поиск показателей в справочнике. GET ?q=...&category=...&exclude_standard=..."""
    if not _check_access(request.user):
        return JsonResponse({'error': 'Нет доступа'}, status=403)

    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    exclude_standard = request.GET.get('exclude_standard', '').strip()

    params = Parameter.objects.filter(is_active=True)

    if q:
        params = params.filter(
            Q(name__icontains=q) | Q(name_en__icontains=q) | Q(unit__icontains=q)
        )

    if category:
        params = params.filter(category=category)

    if exclude_standard:
        try:
            std_id = int(exclude_standard)
            linked_param_ids = StandardParameter.objects.filter(
                standard_id=std_id, is_active=True
            ).values_list('parameter_id', flat=True)
            params = params.exclude(id__in=linked_param_ids)
        except (ValueError, TypeError):
            pass

    params = params.order_by('display_order', 'name')[:30]

    results = [
        {
            'id': p.id,
            'name': p.name,
            'name_en': p.name_en or '',
            'unit': p.unit or '',
            'category': p.category,
            'category_display': p.get_category_display(),
            'display_name': p.display_name,
        }
        for p in params
    ]

    return JsonResponse({'results': results})


# ============================================================
# AJAX: Создание нового показателя в справочнике
# ============================================================

@login_required
@require_POST
def api_parameter_create(request):
    """Создание нового показателя в справочнике parameters."""
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав на создание'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Название обязательно'}, status=400)

    unit = data.get('unit', '').strip() or None
    category = data.get('category', 'OTHER')

    if category not in [c[0] for c in ParameterCategory.choices]:
        category = 'OTHER'

    if Parameter.objects.filter(name=name, unit=unit).exists():
        existing = Parameter.objects.get(name=name, unit=unit)
        return JsonResponse({
            'error': f'Показатель «{existing.display_name}» уже существует',
            'existing_id': existing.id,
        }, status=400)

    param = Parameter.objects.create(
        name=name,
        name_en=data.get('name_en', '').strip() or None,
        unit=unit,
        description=data.get('description', '').strip() or None,
        category=category,
    )

    log_action(
        request,
        entity_type='parameter',
        entity_id=param.id,
        action='created',
        extra_data={'name': param.name, 'unit': param.unit, 'category': param.category},
    )

    return JsonResponse({
        'success': True,
        'id': param.id,
        'name': param.name,
        'name_en': param.name_en or '',
        'unit': param.unit or '',
        'category': param.category,
        'category_display': param.get_category_display(),
        'display_name': param.display_name,
    })


# ============================================================
# AJAX: Сохранение порядка показателей
# ============================================================

@login_required
@require_POST
def api_parameter_reorder(request):
    """Сохранение порядка показателей стандарта."""
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    standard_id = data.get('standard_id')
    order = data.get('order', [])

    if not standard_id or not order:
        return JsonResponse({'error': 'standard_id и order обязательны'}, status=400)

    for idx, sp_id in enumerate(order):
        StandardParameter.objects.filter(
            id=sp_id, standard_id=standard_id
        ).update(display_order=idx * 10)

    return JsonResponse({'success': True})


# ============================================================
# AJAX: Управление исключениями из допуска ⭐ v3.28.0
# ============================================================

@login_required
@require_POST
def api_standard_toggle_exclusion(request):
    """
    Исключить или вернуть допуск сотрудника к стандарту.

    POST JSON:
      standard_id  — ID стандарта
      user_id      — ID сотрудника
      exclude      — true (исключить) или false (вернуть допуск)
      reason       — причина исключения (опционально)
    """
    if not _can_edit(request.user):
        return JsonResponse({'error': 'Нет прав на редактирование'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    standard_id = data.get('standard_id')
    user_id = data.get('user_id')
    exclude = data.get('exclude', True)
    reason = data.get('reason', '').strip() or None

    if not standard_id or not user_id:
        return JsonResponse({'error': 'standard_id и user_id обязательны'}, status=400)

    from core.models import User as UserModel
    target_user = get_object_or_404(UserModel, pk=user_id)
    standard = get_object_or_404(Standard, pk=standard_id)

    with connection.cursor() as cur:
        if exclude:
            cur.execute(
                "INSERT INTO user_standard_exclusions (user_id, standard_id, excluded_by_id, reason) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, standard_id) DO UPDATE SET "
                "excluded_by_id = %s, reason = %s, excluded_at = CURRENT_TIMESTAMP",
                [user_id, standard_id, request.user.pk, reason,
                 request.user.pk, reason]
            )
            action_name = 'user_excluded_from_standard'
            msg = f'{target_user.full_name} исключён из допуска к {standard.code}'
        else:
            cur.execute(
                "DELETE FROM user_standard_exclusions WHERE user_id = %s AND standard_id = %s",
                [user_id, standard_id]
            )
            action_name = 'user_included_to_standard'
            msg = f'{target_user.full_name} возвращён в допуск к {standard.code}'

    # Аудит
    log_action(
        request,
        entity_type='standard',
        entity_id=standard_id,
        action=action_name,
        extra_data={
            'user_id': user_id,
            'user_name': target_user.full_name,
            'standard_code': standard.code,
            'reason': reason,
        },
    )

    return JsonResponse({'success': True, 'message': msg})

