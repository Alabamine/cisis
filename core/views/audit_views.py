"""
CISIS v3.18.0 — Views для журнала аудита.

Файл: core/views/audit_views.py
Действие: ПОЛНАЯ ЗАМЕНА

Содержит:
- audit_log_view: страница журнала аудита с фильтрами и пагинацией
- _resolve_field_display: человекочитаемое название поля
- _resolve_value_display: человекочитаемое значение (статусы, FK, даты, bool)

⭐ v3.16.0: Человекочитаемые значения в столбцах «Поле», «Было», «Стало»
⭐ v3.18.0: Доступ через PermissionChecker (убран хардкод AUDIT_ALLOWED_ROLES)
"""

import re
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q

from core.models import (
    AuditLog, User, JournalColumn,
    SampleStatus, WorkshopStatus, ReportType, FurtherMovement,
    Laboratory, Client, Contract, Standard, AccreditationArea, Equipment,
)
from core.permissions import PermissionChecker


AUDIT_ITEMS_PER_PAGE = 50

# Человекочитаемые названия типов сущностей
ENTITY_TYPE_LABELS = {
    'sample': 'Образец',
    'equipment': 'Оборудование',
    'measuring_instrument': 'Средство измерения',
    'standard': 'Стандарт',
    'user': 'Пользователь',
    'protocol': 'Протокол',
    'climate_log': 'Журнал климатики',
}

# Человекочитаемые названия действий
ACTION_LABELS = {
    'create': 'Создание',
    'update': 'Изменение',
    'status_change': 'Смена статуса',
    'delete': 'Удаление',
    'm2m_add': 'Добавление связи',
    'm2m_remove': 'Удаление связи',
    'view': 'Просмотр',
}


# ─────────────────────────────────────────────────────────────
# Резолверы для человекочитаемого отображения
# ─────────────────────────────────────────────────────────────

# Кэш: field_code → display_name (из journal_columns)
_field_name_cache = None


def _get_field_name_map():
    """Загружает маппинг code → name из journal_columns (с кэшированием)."""
    global _field_name_cache
    if _field_name_cache is None:
        _field_name_cache = dict(
            JournalColumn.objects.filter(
                journal__code='SAMPLES', is_active=True
            ).values_list('code', 'name')
        )
    return _field_name_cache


def _resolve_field_display(field_code):
    """Преобразует код поля в человекочитаемое название."""
    if not field_code:
        return None
    name_map = _get_field_name_map()
    return name_map.get(field_code, field_code)


# Словари choices для быстрого поиска
_STATUS_MAP = dict(SampleStatus.choices)
_WORKSHOP_STATUS_MAP = dict(WorkshopStatus.choices)

try:
    _REPORT_TYPE_MAP = dict(ReportType.choices)
except Exception:
    _REPORT_TYPE_MAP = {}

try:
    _FURTHER_MOVEMENT_MAP = dict(FurtherMovement.choices)
except Exception:
    _FURTHER_MOVEMENT_MAP = {}

# Поля, значения которых — ID пользователей
_USER_FK_FIELDS = frozenset([
    'registered_by', 'verified_by', 'report_prepared_by',
    'protocol_checked_by', 'report_prepared_by',
])

# Поля, значения которых — ID оборудования
_EQUIPMENT_FK_FIELDS = frozenset([
    'measuring_instruments', 'testing_equipment', 'auxiliary_equipment',
    'manufacturing_measuring_instruments', 'manufacturing_testing_equipment',
    'manufacturing_auxiliary_equipment',
])

# Поля, значения которых — ID операторов (M2M users)
_OPERATOR_M2M_FIELDS = frozenset([
    'operators', 'manufacturing_operators',
])

# Поля с датой/временем (ISO строки в audit_log)
_DATETIME_FIELDS = frozenset([
    'conditioning_start_datetime', 'conditioning_end_datetime',
    'testing_start_datetime', 'testing_end_datetime',
    'report_prepared_date', 'manufacturing_completion_date',
    'verified_at',
])

_DATE_FIELDS = frozenset([
    'registration_date', 'deadline', 'manufacturing_deadline',
    'contract_date', 'sample_received_date',
    'protocol_issued_date', 'protocol_printed_date',
    'replacement_protocol_issued_date',
])

# Regex для обнаружения ISO datetime строк
_ISO_DATETIME_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}'
)
_ISO_DATE_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}$'
)

# Кэши для FK-резолвинга (заполняются лениво)
_user_cache = {}
_equipment_cache = {}
_laboratory_cache = {}
_client_cache = {}
_standard_cache = {}
_accreditation_area_cache = {}
_contract_cache = {}


def _resolve_user(user_id):
    """Резолвит ID пользователя в ФИО."""
    if user_id not in _user_cache:
        try:
            u = User.objects.filter(id=int(user_id)).values_list(
                'first_name', 'last_name'
            ).first()
            if u:
                _user_cache[user_id] = f'{u[0]} {u[1]}'.strip()
            else:
                _user_cache[user_id] = f'ID {user_id}'
        except (ValueError, TypeError):
            _user_cache[user_id] = str(user_id)
    return _user_cache[user_id]


def _resolve_equipment(eq_id):
    """Резолвит ID оборудования в учётный номер + название."""
    if eq_id not in _equipment_cache:
        try:
            eq = Equipment.objects.filter(id=int(eq_id)).values_list(
                'accounting_number', 'name'
            ).first()
            if eq:
                _equipment_cache[eq_id] = f'{eq[0]} — {eq[1]}'
            else:
                _equipment_cache[eq_id] = f'ID {eq_id}'
        except (ValueError, TypeError):
            _equipment_cache[eq_id] = str(eq_id)
    return _equipment_cache[eq_id]


def _resolve_laboratory(lab_id):
    """Резолвит ID лаборатории."""
    if lab_id not in _laboratory_cache:
        try:
            lab = Laboratory.objects.filter(id=int(lab_id)).values_list(
                'code_display', 'name'
            ).first()
            if lab:
                _laboratory_cache[lab_id] = f'{lab[0]} — {lab[1]}'
            else:
                _laboratory_cache[lab_id] = f'ID {lab_id}'
        except (ValueError, TypeError):
            _laboratory_cache[lab_id] = str(lab_id)
    return _laboratory_cache[lab_id]


def _resolve_client(client_id):
    """Резолвит ID заказчика."""
    if client_id not in _client_cache:
        try:
            c = Client.objects.filter(id=int(client_id)).values_list('name', flat=True).first()
            _client_cache[client_id] = c or f'ID {client_id}'
        except (ValueError, TypeError):
            _client_cache[client_id] = str(client_id)
    return _client_cache[client_id]


def _resolve_standard(std_id):
    """Резолвит ID стандарта."""
    if std_id not in _standard_cache:
        try:
            s = Standard.objects.filter(id=int(std_id)).values_list('code', flat=True).first()
            _standard_cache[std_id] = s or f'ID {std_id}'
        except (ValueError, TypeError):
            _standard_cache[std_id] = str(std_id)
    return _standard_cache[std_id]


def _resolve_accreditation_area(area_id):
    """Резолвит ID области аккредитации."""
    if area_id not in _accreditation_area_cache:
        try:
            a = AccreditationArea.objects.filter(id=int(area_id)).values_list(
                'code', flat=True
            ).first()
            _accreditation_area_cache[area_id] = a or f'ID {area_id}'
        except (ValueError, TypeError):
            _accreditation_area_cache[area_id] = str(area_id)
    return _accreditation_area_cache[area_id]


def _resolve_contract(contract_id):
    """Резолвит ID договора."""
    if contract_id not in _contract_cache:
        try:
            c = Contract.objects.filter(id=int(contract_id)).values_list(
                'number', flat=True
            ).first()
            _contract_cache[contract_id] = c or f'ID {contract_id}'
        except (ValueError, TypeError):
            _contract_cache[contract_id] = str(contract_id)
    return _contract_cache[contract_id]


def _format_datetime(value_str):
    """Форматирует ISO datetime строку в dd.mm.YYYY HH:MM."""
    if not value_str:
        return value_str
    try:
        clean = value_str.strip()
        for fmt in (
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S.%f%z',
            '%Y-%m-%d %H:%M:%S%z',
            '%Y-%m-%d %H:%M:%S.%f%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
        ):
            try:
                dt = datetime.strptime(clean, fmt)
                return dt.strftime('%d.%m.%Y %H:%M')
            except ValueError:
                continue
        # Fallback: попробовать отрезать до минут
        if 'T' in clean or ' ' in clean:
            parts = clean.replace('T', ' ').split('+')[0].split('-0')[0]
            if len(parts) >= 16:
                dt = datetime.strptime(parts[:16], '%Y-%m-%d %H:%M')
                return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        pass
    return value_str


def _format_date(value_str):
    """Форматирует ISO date строку в dd.mm.YYYY."""
    if not value_str:
        return value_str
    try:
        dt = datetime.strptime(value_str.strip(), '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except (ValueError, AttributeError):
        return value_str


def _resolve_value(field_code, raw_value):
    """
    Преобразует сырое значение из audit_log в человекочитаемое.
    """
    if raw_value is None or raw_value == '' or raw_value == 'None':
        return '—'

    val = str(raw_value).strip()

    # --- Статусы ---
    if field_code == 'status':
        return _STATUS_MAP.get(val, val)

    if field_code == 'workshop_status':
        return _WORKSHOP_STATUS_MAP.get(val, val)

    if field_code == 'report_type':
        return _REPORT_TYPE_MAP.get(val, val)

    if field_code == 'further_movement':
        return _FURTHER_MOVEMENT_MAP.get(val, val)

    # --- Boolean ---
    if val in ('true', 'True'):
        return 'Да'
    if val in ('false', 'False'):
        return 'Нет'

    # --- FK пользователи ---
    if field_code in _USER_FK_FIELDS:
        return _resolve_user(val)

    # --- FK оборудование (для обычных update) ---
    if field_code in _EQUIPMENT_FK_FIELDS:
        return _resolve_equipment(val)

    # --- M2M операторы (могут быть списком ID через запятую) ---
    if field_code in _OPERATOR_M2M_FIELDS:
        ids = [x.strip() for x in val.split(',') if x.strip()]
        if ids and all(x.isdigit() for x in ids):
            return ', '.join(_resolve_user(uid) for uid in ids)
        return val

    # --- M2M оборудование (добавление/удаление связей) ---
    if field_code in _EQUIPMENT_FK_FIELDS:
        ids = [x.strip() for x in val.split(',') if x.strip()]
        if ids and all(x.isdigit() for x in ids):
            return ', '.join(_resolve_equipment(eid) for eid in ids)
        return val

    # --- FK лаборатория ---
    if field_code == 'laboratory':
        if val.isdigit():
            return _resolve_laboratory(val)

    # --- FK заказчик ---
    if field_code == 'client':
        if val.isdigit():
            return _resolve_client(val)

    # --- FK договор ---
    if field_code == 'contract':
        if val.isdigit():
            return _resolve_contract(val)

    # --- FK стандарт / cutting_standard ---
    if field_code in ('standards', 'cutting_standard'):
        ids = [x.strip() for x in val.split(',') if x.strip()]
        if ids and all(x.isdigit() for x in ids):
            return ', '.join(_resolve_standard(sid) for sid in ids)
        return val

    # --- FK область аккредитации ---
    if field_code == 'accreditation_area':
        if val.isdigit():
            return _resolve_accreditation_area(val)

    # --- Datetime поля ---
    if field_code in _DATETIME_FIELDS or _ISO_DATETIME_RE.match(val):
        return _format_datetime(val)

    # --- Date поля ---
    if field_code in _DATE_FIELDS or _ISO_DATE_RE.match(val):
        return _format_date(val)

    return val


def _enrich_entries(entries):
    """
    Добавляет к каждой записи аудита человекочитаемые поля:
    - field_display: название поля
    - old_display: значение «Было»
    - new_display: значение «Стало»
    """
    for entry in entries:
        entry.field_display = _resolve_field_display(entry.field_name)
        entry.old_display = _resolve_value(entry.field_name, entry.old_value)
        entry.new_display = _resolve_value(entry.field_name, entry.new_value)
    return entries


# ─────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────

@login_required
def audit_log_view(request):
    """Страница журнала аудита с фильтрами и пагинацией."""

    # ⭐ v3.18.0: Проверка доступа через PermissionChecker
    if not PermissionChecker.can_view(request.user, 'AUDIT_LOG', 'access'):
        messages.error(request, 'У вас нет доступа к журналу аудита')
        return redirect('workspace_home')

    # Базовый queryset
    queryset = AuditLog.objects.select_related('user').all()

    # ── Фильтры ──
    entity_type = request.GET.get('entity_type', '')
    entity_id = request.GET.get('entity_id', '')
    action = request.GET.get('action', '')
    user_id = request.GET.get('user_id', '')
    field_name = request.GET.get('field_name', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search = request.GET.get('search', '')

    if entity_type:
        queryset = queryset.filter(entity_type=entity_type)
    if entity_id:
        queryset = queryset.filter(entity_id=int(entity_id))
    if action:
        queryset = queryset.filter(action=action)
    if user_id:
        queryset = queryset.filter(user_id=int(user_id))
    if field_name:
        queryset = queryset.filter(field_name__icontains=field_name)
    if date_from:
        queryset = queryset.filter(timestamp__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(timestamp__date__lte=date_to)
    if search:
        queryset = queryset.filter(
            Q(old_value__icontains=search) |
            Q(new_value__icontains=search) |
            Q(field_name__icontains=search)
        )

    # ── Сортировка ──
    sort = request.GET.get('sort', '-timestamp')
    allowed_sorts = {
        'timestamp', '-timestamp', 'user', '-user',
        'action', '-action', 'entity_type', '-entity_type',
    }
    if sort not in allowed_sorts:
        sort = '-timestamp'

    if sort in ('user', '-user'):
        sort_field = sort.replace('user', 'user__username')
    else:
        sort_field = sort
    queryset = queryset.order_by(sort_field)

    # ── Пагинация ──
    page_number = request.GET.get('page', 1)
    paginator = Paginator(queryset, AUDIT_ITEMS_PER_PAGE)
    page_obj = paginator.get_page(page_number)

    # ⭐ v3.16.0: Обогащаем записи человекочитаемыми значениями
    _enrich_entries(page_obj.object_list)

    # ── Данные для фильтров ──
    active_user_ids = (
        AuditLog.objects.values_list('user_id', flat=True)
        .distinct()
        .order_by('user_id')
    )
    filter_users = User.objects.filter(
        id__in=active_user_ids
    ).order_by('last_name', 'first_name')

    active_entity_types = (
        AuditLog.objects.values_list('entity_type', flat=True)
        .distinct()
        .order_by('entity_type')
    )

    active_actions = (
        AuditLog.objects.values_list('action', flat=True)
        .distinct()
        .order_by('action')
    )

    # ── Строка параметров для ссылок ──
    filter_params = {}
    if entity_type:
        filter_params['entity_type'] = entity_type
    if entity_id:
        filter_params['entity_id'] = entity_id
    if action:
        filter_params['action'] = action
    if user_id:
        filter_params['user_id'] = user_id
    if field_name:
        filter_params['field_name'] = field_name
    if date_from:
        filter_params['date_from'] = date_from
    if date_to:
        filter_params['date_to'] = date_to
    if search:
        filter_params['search'] = search

    from urllib.parse import urlencode
    filter_query = urlencode(filter_params)
    sort_link_params = filter_query
    if sort != '-timestamp':
        filter_query_with_sort = urlencode({**filter_params, 'sort': sort})
    else:
        filter_query_with_sort = filter_query

    context = {
        'page_obj': page_obj,
        'entries': page_obj.object_list,
        'total_count': paginator.count,
        # Фильтры — текущие значения
        'current_entity_type': entity_type,
        'current_entity_id': entity_id,
        'current_action': action,
        'current_user_id': user_id,
        'current_field_name': field_name,
        'current_date_from': date_from,
        'current_date_to': date_to,
        'current_search': search,
        'current_sort': sort,
        # Строки для ссылок
        'filter_query': filter_query_with_sort,
        'sort_link_params': sort_link_params,
        # Данные для выпадающих списков
        'filter_users': filter_users,
        'entity_type_choices': [
            (et, ENTITY_TYPE_LABELS.get(et, et))
            for et in active_entity_types
        ],
        'action_choices': [
            (a, ACTION_LABELS.get(a, a))
            for a in active_actions
        ],
        'entity_type_labels': ENTITY_TYPE_LABELS,
        'action_labels': ACTION_LABELS,
        'user': request.user,
    }

    return render(request, 'core/audit_log.html', context)