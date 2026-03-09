"""
employee_views.py — Справочник сотрудников + Матрица ответственности
v3.28.0

Расположение: core/views/employee_views.py

Новые маршруты в core/urls.py:
    path('workspace/employees/<int:user_id>/save-areas/', employee_views.employee_save_areas, name='employee_save_areas'),
    path('workspace/responsibility-matrix/', employee_views.responsibility_matrix, name='responsibility_matrix'),
    path('api/responsibility-matrix/save/', employee_views.api_save_matrix, name='api_save_matrix'),
"""

import json
import re
import secrets
import string
from urllib.parse import urlencode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Q
from django.views.decorators.http import require_POST

from core.permissions import PermissionChecker
from core.models import User, Laboratory, UserRole
from core.models.base import AccreditationArea

EMPLOYEES_PER_PAGE = 50

# ─────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────

PHONE_RE = re.compile(r'^[\+]?[\d\s\-\(\)]{7,20}$')

MANAGER_ROLES = frozenset({'CEO', 'CTO', 'SYSADMIN'})


def _can_manage_employee(editor, target):
    """
    Может ли editor редактировать target.
    CEO/CTO/SYSADMIN → всех.
    LAB_HEAD → сотрудников своей лаборатории (основная + доп.).
    """
    if not PermissionChecker.can_edit(editor, 'EMPLOYEES', 'access'):
        return False

    if editor.role in MANAGER_ROLES:
        return True

    if editor.role == 'LAB_HEAD':
        editor_lab_ids = editor.all_laboratory_ids
        # Целевой пользователь принадлежит одной из лабораторий редактора?
        if target.laboratory_id and target.laboratory_id in editor_lab_ids:
            return True
        # Проверяем доп. лаборатории целевого пользователя
        target_lab_ids = target.all_laboratory_ids
        if editor_lab_ids & target_lab_ids:
            return True
        return False

    return False


def _can_manage_matrix(user):
    """Может ли пользователь редактировать матрицу ответственности."""
    return PermissionChecker.can_edit(user, 'RESPONSIBILITY_MATRIX', 'access')


def _validate_phone(phone):
    """Валидация телефона. Возвращает (cleaned, error)."""
    if not phone:
        return '', None
    phone = phone.strip()
    if not PHONE_RE.match(phone):
        return phone, 'Некорректный формат телефона'
    return phone, None


def _generate_password(length=10):
    """Генерирует случайный пароль."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _get_user_area_ids(user_id):
    """Получить ID областей аккредитации, к которым допущен сотрудник."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT accreditation_area_id FROM user_accreditation_areas WHERE user_id = %s",
            [user_id]
        )
        return [row[0] for row in cur.fetchall()]


def _get_equipment_for_user(user_id):
    """Получить оборудование, где сотрудник ответственный или замещающий."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                e.id, e.name, e.inventory_number, e.equipment_type,
                e.status, l.code_display AS lab_display,
                CASE
                    WHEN e.responsible_person_id = %s THEN 'responsible'
                    WHEN e.substitute_person_id = %s THEN 'substitute'
                END AS person_role
            FROM equipment e
            LEFT JOIN laboratories l ON l.id = e.laboratory_id
            WHERE e.responsible_person_id = %s OR e.substitute_person_id = %s
            ORDER BY
                CASE WHEN e.responsible_person_id = %s THEN 0 ELSE 1 END,
                e.equipment_type, e.name
        """, [user_id, user_id, user_id, user_id, user_id])

        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


# ─────────────────────────────────────────────────────────────
# Список сотрудников
# ─────────────────────────────────────────────────────────────

@login_required
def employees_list(request):
    if not PermissionChecker.can_view(request.user, 'EMPLOYEES', 'access'):
        messages.error(request, 'У вас нет доступа к справочнику сотрудников')
        return redirect('workspace_home')

    can_edit = PermissionChecker.can_edit(request.user, 'EMPLOYEES', 'access')

    # ── Фильтры ───────────────────────────────────────────────
    search       = request.GET.get('search', '').strip()
    lab_id       = request.GET.get('lab_id', '')
    role_filter  = request.GET.get('role', '')
    show_inactive = request.GET.get('show_inactive', '')

    qs = User.objects.select_related('laboratory', 'mentor')

    # По умолчанию скрываем деактивированных
    if not show_inactive:
        qs = qs.filter(is_active=True)

    if search:
        qs = qs.filter(
            Q(last_name__icontains=search) |
            Q(first_name__icontains=search) |
            Q(sur_name__icontains=search) |
            Q(username__icontains=search) |
            Q(position__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )

    if lab_id:
        qs = qs.filter(laboratory_id=int(lab_id))

    if role_filter:
        qs = qs.filter(role=role_filter)

    # ── Сортировка ────────────────────────────────────────────
    sort = request.GET.get('sort', 'last_name')
    allowed_sorts = {
        'last_name', '-last_name',
        'position', '-position',
        'laboratory', '-laboratory',
        'role', '-role',
    }
    if sort not in allowed_sorts:
        sort = 'last_name'

    if sort in ('laboratory', '-laboratory'):
        order_field = 'laboratory__name' if sort == 'laboratory' else '-laboratory__name'
    else:
        order_field = sort

    qs = qs.order_by(order_field, 'last_name', 'first_name')

    # ── Пагинация ─────────────────────────────────────────────
    total_count = qs.count()
    paginator = Paginator(qs, EMPLOYEES_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Справочники для фильтров
    laboratories = Laboratory.objects.filter(is_active=True).order_by('name')
    roles = UserRole.choices

    # Показывать чекбокс «Деактивированные» только тем, кто может редактировать
    show_inactive_toggle = can_edit

    # Параметры фильтров для пагинации
    filter_params = {}
    if search:        filter_params['search']        = search
    if lab_id:        filter_params['lab_id']        = lab_id
    if role_filter:   filter_params['role']          = role_filter
    if show_inactive: filter_params['show_inactive'] = show_inactive
    if sort != 'last_name': filter_params['sort']    = sort

    context = {
        'page_obj':              page_obj,
        'employees':             page_obj.object_list,
        'total_count':           total_count,
        'laboratories':          laboratories,
        'roles':                 roles,
        'can_edit':              can_edit,
        'show_inactive_toggle':  show_inactive_toggle,
        'current_search':        search,
        'current_lab_id':        lab_id,
        'current_role':          role_filter,
        'current_show_inactive': show_inactive,
        'current_sort':          sort,
        'filter_query':          urlencode(filter_params),
        'sort_link_params':      urlencode({k: v for k, v in filter_params.items() if k != 'sort'}),
    }
    return render(request, 'core/employees.html', context)


# ─────────────────────────────────────────────────────────────
# Карточка сотрудника
# ─────────────────────────────────────────────────────────────

@login_required
def employee_detail(request, user_id):
    if not PermissionChecker.can_view(request.user, 'EMPLOYEES', 'access'):
        messages.error(request, 'У вас нет доступа к справочнику сотрудников')
        return redirect('workspace_home')

    employee = get_object_or_404(User, pk=user_id)
    can_manage = _can_manage_employee(request.user, employee)
    is_self = (request.user.pk == employee.pk)

    # Роль — красивое отображение
    role_display = dict(UserRole.choices).get(employee.role, employee.role)

    # Наставник
    mentor_name = employee.mentor.full_name if employee.mentor_id else None

    # Стажёры (если этот пользователь — наставник)
    trainees = User.objects.filter(
        mentor=employee, is_active=True
    ).order_by('last_name', 'first_name')

    # ── Оборудование ⭐ v3.28.0 ──────────────────────────────
    equipment_list = _get_equipment_for_user(employee.pk)
    equipment_responsible = [e for e in equipment_list if e['person_role'] == 'responsible']
    equipment_substitute  = [e for e in equipment_list if e['person_role'] == 'substitute']

    # ── Области аккредитации ⭐ v3.28.0 ───────────────────────
    user_area_ids = _get_user_area_ids(employee.pk)
    all_areas = AccreditationArea.objects.filter(is_active=True).order_by('name')

    # Исключения по стандартам
    standard_exclusions = []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT use.standard_id, s.code, s.name, use.reason
            FROM user_standard_exclusions use
            JOIN standards s ON s.id = use.standard_id
            WHERE use.user_id = %s
            ORDER BY s.code
        """, [employee.pk])
        for row in cur.fetchall():
            standard_exclusions.append({
                'standard_id': row[0],
                'code': row[1],
                'name': row[2],
                'reason': row[3],
            })

    # Можно ли редактировать допуски (матрицу ответственности)
    can_manage_areas = _can_manage_matrix(request.user)
    # LAB_HEAD может редактировать допуски только для своих сотрудников
    if not can_manage_areas and request.user.role == 'LAB_HEAD':
        can_manage_areas = _can_manage_employee(request.user, employee)

    context = {
        'employee':              employee,
        'role_display':          role_display,
        'mentor_name':           mentor_name,
        'trainees':              trainees,
        'can_manage':            can_manage,
        'is_self':               is_self,
        'equipment_responsible': equipment_responsible,
        'equipment_substitute':  equipment_substitute,
        'user_area_ids':         user_area_ids,
        'all_areas':             all_areas,
        'can_manage_areas':      can_manage_areas,
        'standard_exclusions':   standard_exclusions,
    }
    return render(request, 'core/employee_detail.html', context)


# ─────────────────────────────────────────────────────────────
# Сохранение областей аккредитации сотрудника ⭐ v3.28.0
# ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def employee_save_areas(request, user_id):
    """Сохранить области аккредитации для сотрудника."""
    employee = get_object_or_404(User, pk=user_id)

    # Проверка прав
    can_edit_areas = _can_manage_matrix(request.user)
    if not can_edit_areas and request.user.role == 'LAB_HEAD':
        can_edit_areas = _can_manage_employee(request.user, employee)
    if not can_edit_areas:
        return HttpResponseForbidden()

    area_ids = request.POST.getlist('area_ids')  # список строк
    area_ids_int = [int(a) for a in area_ids if a.isdigit()]

    old_area_ids = set(_get_user_area_ids(employee.pk))
    new_area_ids = set(area_ids_int)

    with connection.cursor() as cur:
        # Удалить снятые
        to_remove = old_area_ids - new_area_ids
        if to_remove:
            cur.execute(
                "DELETE FROM user_accreditation_areas WHERE user_id = %s AND accreditation_area_id = ANY(%s)",
                [employee.pk, list(to_remove)]
            )

        # Добавить новые
        to_add = new_area_ids - old_area_ids
        for area_id in to_add:
            cur.execute(
                "INSERT INTO user_accreditation_areas (user_id, accreditation_area_id, assigned_by_id) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                [employee.pk, area_id, request.user.pk]
            )

    # Аудит
    if to_remove or to_add:
        try:
            from core.views.audit import log_action

            # Получаем названия областей для лога
            areas_map = dict(AccreditationArea.objects.values_list('id', 'name'))
            added_names = [areas_map.get(a, str(a)) for a in to_add]
            removed_names = [areas_map.get(a, str(a)) for a in to_remove]

            log_action(
                    request, 'USER', employee.pk, 'EMPLOYEE_AREAS_CHANGED',
                    extra_data={
                    'employee': employee.full_name,
                    'added': added_names,
                    'removed': removed_names,
                }
            )
        except Exception:
            pass

    messages.success(request, f'Области аккредитации для {employee.full_name} обновлены')
    return redirect('employee_detail', user_id=employee.pk)


# ─────────────────────────────────────────────────────────────
# Редактирование сотрудника
# ─────────────────────────────────────────────────────────────

@login_required
def employee_edit(request, user_id):
    employee = get_object_or_404(User, pk=user_id)

    if not _can_manage_employee(request.user, employee):
        messages.error(request, 'У вас нет прав для редактирования этого сотрудника')
        return redirect('employee_detail', user_id=user_id)

    laboratories = Laboratory.objects.filter(is_active=True).order_by('name')
    roles = UserRole.choices
    mentors = User.objects.filter(
        is_active=True, is_trainee=False
    ).exclude(pk=employee.pk).order_by('last_name', 'first_name')

    if request.method == 'POST':
        errors = []

        # Собираем данные
        last_name  = request.POST.get('last_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        sur_name   = request.POST.get('sur_name', '').strip()
        position   = request.POST.get('position', '').strip() or None
        lab_id     = request.POST.get('laboratory', '').strip()
        role       = request.POST.get('role', '').strip()
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()
        is_trainee = request.POST.get('is_trainee') == 'on'
        mentor_id  = request.POST.get('mentor', '').strip() or None

        # Валидация
        if not last_name:
            errors.append('Фамилия обязательна')
        if not first_name:
            errors.append('Имя обязательно')

        phone_clean, phone_err = _validate_phone(phone)
        if phone_err:
            errors.append(phone_err)

        if is_trainee and not mentor_id:
            errors.append('Для стажёра обязательно указать наставника')

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            employee.last_name  = last_name
            employee.first_name = first_name
            employee.sur_name   = sur_name
            employee.position   = position
            employee.laboratory_id = int(lab_id) if lab_id else None
            employee.role       = role
            employee.email      = email
            employee.phone      = phone_clean
            employee.is_trainee = is_trainee
            employee.mentor_id  = int(mentor_id) if mentor_id else None

            try:
                employee.save()

                # Аудит
                try:
                    from core.views.audit import log_action
                    log_action(
                            request, 'USER', employee.pk, 'EMPLOYEE_EDIT',
                            extra_data={'employee': employee.full_name}
                    )
                except Exception:
                    pass

                messages.success(request, f'Сотрудник {employee.full_name} обновлён')
                return redirect('employee_detail', user_id=employee.pk)
            except Exception as e:
                messages.error(request, f'Ошибка сохранения: {e}')

    context = {
        'employee':     employee,
        'laboratories': laboratories,
        'roles':        roles,
        'mentors':      mentors,
        'is_new':       False,
    }
    return render(request, 'core/employee_edit.html', context)


# ─────────────────────────────────────────────────────────────
# Добавление сотрудника
# ─────────────────────────────────────────────────────────────

@login_required
def employee_add(request):
    if not PermissionChecker.can_edit(request.user, 'EMPLOYEES', 'access'):
        messages.error(request, 'У вас нет прав для добавления сотрудников')
        return redirect('employees')

    laboratories = Laboratory.objects.filter(is_active=True).order_by('name')
    roles = UserRole.choices
    mentors = User.objects.filter(
        is_active=True, is_trainee=False
    ).order_by('last_name', 'first_name')

    # Пустой «сотрудник» для шаблона
    employee = None

    if request.method == 'POST':
        errors = []

        username   = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        sur_name   = request.POST.get('sur_name', '').strip()
        position   = request.POST.get('position', '').strip() or None
        lab_id     = request.POST.get('laboratory', '').strip()
        role       = request.POST.get('role', '').strip() or 'OTHER'
        email      = request.POST.get('email', '').strip()
        phone      = request.POST.get('phone', '').strip()
        is_trainee = request.POST.get('is_trainee') == 'on'
        mentor_id  = request.POST.get('mentor', '').strip() or None

        # Валидация
        if not username:
            errors.append('Логин обязателен')
        elif User.objects.filter(username=username).exists():
            errors.append(f'Логин «{username}» уже занят')
        if not password:
            errors.append('Пароль обязателен')
        elif len(password) < 4:
            errors.append('Пароль слишком короткий (минимум 4 символа)')
        if not last_name:
            errors.append('Фамилия обязательна')
        if not first_name:
            errors.append('Имя обязательно')

        phone_clean, phone_err = _validate_phone(phone)
        if phone_err:
            errors.append(phone_err)

        if is_trainee and not mentor_id:
            errors.append('Для стажёра обязательно указать наставника')

        if errors:
            for err in errors:
                messages.error(request, err)
            # Сохраняем введённые данные для повторного заполнения
            employee = {
                'username': username, 'last_name': last_name,
                'first_name': first_name, 'sur_name': sur_name,
                'position': position, 'laboratory_id': int(lab_id) if lab_id else None,
                'role': role, 'email': email, 'phone': phone,
                'is_trainee': is_trainee, 'mentor_id': int(mentor_id) if mentor_id else None,
            }
        else:
            try:
                new_user = User(
                    username=username,
                    last_name=last_name,
                    first_name=first_name,
                    sur_name=sur_name,
                    position=position,
                    laboratory_id=int(lab_id) if lab_id else None,
                    role=role,
                    email=email,
                    phone=phone_clean,
                    is_trainee=is_trainee,
                    mentor_id=int(mentor_id) if mentor_id else None,
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
                new_user.set_password(password)
                new_user.save()

                # Аудит
                try:
                    from core.views.audit import log_action
                    log_action(
                            request, 'USER', new_user.pk, 'EMPLOYEE_ADD',
                            extra_data={'employee': new_user.full_name}
                    )
                except Exception:
                    pass

                messages.success(request, f'Сотрудник {new_user.full_name} добавлен')
                return redirect('employee_detail', user_id=new_user.pk)
            except Exception as e:
                messages.error(request, f'Ошибка создания: {e}')

    context = {
        'employee':     employee,
        'laboratories': laboratories,
        'roles':        roles,
        'mentors':      mentors,
        'is_new':       True,
    }
    return render(request, 'core/employee_edit.html', context)


# ─────────────────────────────────────────────────────────────
# Деактивация / активация
# ─────────────────────────────────────────────────────────────

@login_required
def employee_deactivate(request, user_id):
    if request.method != 'POST':
        return redirect('employee_detail', user_id=user_id)

    employee = get_object_or_404(User, pk=user_id)

    if not _can_manage_employee(request.user, employee):
        return HttpResponseForbidden()

    if employee.pk == request.user.pk:
        messages.error(request, 'Нельзя деактивировать самого себя')
        return redirect('employee_detail', user_id=user_id)

    employee.is_active = False
    employee.save()

    try:
        from core.views.audit import log_action
        log_action(
                request, 'USER', employee.pk, 'EMPLOYEE_DEACTIVATE',
                extra_data={'employee': employee.full_name}
        )
    except Exception:
        pass

    messages.success(request, f'Сотрудник {employee.full_name} деактивирован')
    return redirect('employee_detail', user_id=user_id)


@login_required
def employee_activate(request, user_id):
    if request.method != 'POST':
        return redirect('employee_detail', user_id=user_id)

    employee = get_object_or_404(User, pk=user_id)

    if not _can_manage_employee(request.user, employee):
        return HttpResponseForbidden()

    employee.is_active = True
    employee.save()

    try:
        from core.views.audit import log_action
        log_action(
                request, 'USER', employee.pk, 'EMPLOYEE_ACTIVATE',
                extra_data={'employee': employee.full_name}
        )
    except Exception:
        pass

    messages.success(request, f'Сотрудник {employee.full_name} активирован')
    return redirect('employee_detail', user_id=user_id)


# ─────────────────────────────────────────────────────────────
# Сброс пароля (админом)
# ─────────────────────────────────────────────────────────────

@login_required
def employee_reset_password(request, user_id):
    if request.method != 'POST':
        return redirect('employee_detail', user_id=user_id)

    employee = get_object_or_404(User, pk=user_id)

    if not _can_manage_employee(request.user, employee):
        return HttpResponseForbidden()

    new_password = _generate_password()
    employee.set_password(new_password)
    employee.save()

    try:
        from core.views.audit import log_action
        log_action(
                request, 'USER', employee.pk, 'EMPLOYEE_RESET_PASSWORD',
                extra_data={'employee': employee.full_name}
        )
    except Exception:
        pass

    messages.success(
        request,
        f'Пароль для {employee.full_name} сброшен. '
        f'Новый пароль: {new_password} — запишите его, он больше не будет показан!'
    )
    return redirect('employee_detail', user_id=user_id)


# ─────────────────────────────────────────────────────────────
# Смена своего пароля
# ─────────────────────────────────────────────────────────────

@login_required
def change_password(request):
    if request.method == 'POST':
        old_password     = request.POST.get('old_password', '')
        new_password     = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        errors = []

        if not request.user.check_password(old_password):
            errors.append('Текущий пароль указан неверно')
        if len(new_password) < 4:
            errors.append('Новый пароль слишком короткий (минимум 4 символа)')
        if new_password != confirm_password:
            errors.append('Пароли не совпадают')
        if old_password and new_password == old_password:
            errors.append('Новый пароль совпадает с текущим')

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, 'Пароль успешно изменён')
            return redirect('workspace_home')

    return render(request, 'core/change_password.html')


# ─────────────────────────────────────────────────────────────
# AJAX: проверка уникальности username
# ─────────────────────────────────────────────────────────────

@login_required
def api_check_username(request):
    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'available': False, 'error': 'Пустой логин'})

    exists = User.objects.filter(username=username).exists()
    return JsonResponse({'available': not exists})


# ─────────────────────────────────────────────────────────────
# Матрица ответственности ⭐ v3.28.0
# ─────────────────────────────────────────────────────────────

@login_required
def responsibility_matrix(request):
    """Страница «Матрица ответственности» — сотрудники × области аккредитации."""
    if not PermissionChecker.can_view(request.user, 'RESPONSIBILITY_MATRIX', 'access'):
        messages.error(request, 'У вас нет доступа к матрице ответственности')
        return redirect('workspace_home')

    can_edit = _can_manage_matrix(request.user)

    # ── Фильтры ───────────────────────────────────────────────
    lab_filter = request.GET.get('lab_id', '')
    search = request.GET.get('search', '').strip()

    # Области аккредитации (без «Вне области»)
    areas = AccreditationArea.objects.filter(
        is_active=True, is_default=False
    ).order_by('name')

    # Сотрудники
    users_qs = User.objects.filter(is_active=True).select_related('laboratory')

    if lab_filter:
        users_qs = users_qs.filter(laboratory_id=int(lab_filter))

    if search:
        users_qs = users_qs.filter(
            Q(last_name__icontains=search) |
            Q(first_name__icontains=search) |
            Q(sur_name__icontains=search)
        )

    users_qs = users_qs.order_by('laboratory__code_display', 'last_name', 'first_name')

    # Загружаем все допуски одним запросом
    with connection.cursor() as cur:
        cur.execute("SELECT user_id, accreditation_area_id FROM user_accreditation_areas")
        all_assignments = cur.fetchall()

    # Множество (user_id, area_id)
    assignment_set = {(row[0], row[1]) for row in all_assignments}

    # Собираем данные для шаблона
    matrix_rows = []
    for user in users_qs:
        row = {
            'user': user,
            'areas': []
        }
        for area in areas:
            row['areas'].append({
                'area_id': area.id,
                'checked': (user.pk, area.id) in assignment_set,
            })
        matrix_rows.append(row)

    # Лаборатории для фильтра
    laboratories = Laboratory.objects.filter(
        is_active=True, department_type='LAB'
    ).order_by('code_display')

    context = {
        'areas':          areas,
        'matrix_rows':    matrix_rows,
        'can_edit':       can_edit,
        'laboratories':   laboratories,
        'current_lab_id': lab_filter,
        'current_search': search,
        'total_users':    len(matrix_rows),
    }
    return render(request, 'core/responsibility_matrix.html', context)


@login_required
@require_POST
def api_save_matrix(request):
    """AJAX: сохранить изменения матрицы ответственности."""
    if not _can_manage_matrix(request.user):
        return JsonResponse({'error': 'Нет прав на редактирование'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    changes = data.get('changes', [])
    # changes = [{'user_id': 5, 'area_id': 2, 'checked': True}, ...]

    if not changes:
        return JsonResponse({'success': True, 'count': 0})

    added = 0
    removed = 0

    with connection.cursor() as cur:
        for ch in changes:
            user_id = int(ch['user_id'])
            area_id = int(ch['area_id'])
            checked = ch['checked']

            if checked:
                cur.execute(
                    "INSERT INTO user_accreditation_areas (user_id, accreditation_area_id, assigned_by_id) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    [user_id, area_id, request.user.pk]
                )
                if cur.rowcount > 0:
                    added += 1
            else:
                cur.execute(
                    "DELETE FROM user_accreditation_areas "
                    "WHERE user_id = %s AND accreditation_area_id = %s",
                    [user_id, area_id]
                )
                if cur.rowcount > 0:
                    removed += 1

    # Аудит
    if added or removed:
        try:
            from core.views.audit import log_action
            log_action(
                    request, 'RESPONSIBILITY_MATRIX', 0, 'MATRIX_BULK_UPDATE',
                    extra_data={
                    'added': added,
                    'removed': removed,
                    'total_changes': len(changes),
                }
            )
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'added': added,
        'removed': removed,
    })