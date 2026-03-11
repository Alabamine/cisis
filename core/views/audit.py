# ============================================================
# CISIS v3.14.0 — Утилиты аудит-лога
# Файл: core/views/audit.py
# ============================================================

import json
import logging
from typing import Any, Optional

from core.models import AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request) -> Optional[str]:
    """Извлекает IP-адрес клиента из запроса."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _serialize_value(value) -> Optional[str]:
    """Приводит значение к строке для хранения в audit_log."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def log_action(
    request,
    entity_type: str,
    entity_id: int,
    action: str,
    field_name: str = None,
    old_value: Any = None,
    new_value: Any = None,
    extra_data: dict = None,
):
    """
    Записывает одно действие в журнал аудита.

    Использование:
        from core.views.audit import log_action

        # Простое действие
        log_action(request, 'sample', sample.id, 'create')

        # Изменение поля
        log_action(request, 'sample', sample.id, 'update',
                   field_name='status', old_value='REGISTERED', new_value='IN_TESTING')

        # M2M изменение
        log_action(request, 'sample', sample.id, 'm2m_add',
                   field_name='standards', new_value='ГОСТ 12345',
                   extra_data={'standard_ids': [1, 2, 3]})
    """
    try:
        AuditLog.objects.create(
            user=request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field_name=field_name,
            old_value=_serialize_value(old_value),
            new_value=_serialize_value(new_value),
            ip_address=get_client_ip(request) if request else None,
            extra_data=extra_data,
        )
    except Exception as e:
        # Аудит-лог не должен ломать основной функционал
        logger.error(f"Ошибка записи audit_log: {e}")


def log_field_changes(
    request,
    entity_type: str,
    entity_id: int,
    changes: dict,
    extra_data: dict = None,
):
    """
    Записывает пакет изменений полей за одно сохранение.

    changes = {
        'field_name': (old_value, new_value),
        'status': ('REGISTERED', 'IN_TESTING'),
        'temperature': (None, '23.5'),
    }
    """
    for field, (old_val, new_val) in changes.items():
        # Определяем тип действия
        if field == 'status':
            action = 'status_change'
        else:
            action = 'update'

        log_action(
            request=request,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field_name=field,
            old_value=old_val,
            new_value=new_val,
            extra_data=extra_data,
        )


def log_m2m_changes(
    request,
    entity_type: str,
    entity_id: int,
    field_name: str,
    old_ids: set,
    new_ids: set,
    id_to_label: dict = None,
):
    """
    Логирует изменения M2M-связей (добавление / удаление).

    old_ids, new_ids — множества ID связанных объектов.
    id_to_label — опциональный словарь {id: "человекочитаемое название"}.
    """
    added = new_ids - old_ids
    removed = old_ids - new_ids

    if not added and not removed:
        return

    def _label(obj_id):
        if id_to_label and obj_id in id_to_label:
            return id_to_label[obj_id]
        return str(obj_id)

    if added:
        log_action(
            request=request,
            entity_type=entity_type,
            entity_id=entity_id,
            action='m2m_add',
            field_name=field_name,
            new_value=', '.join(_label(i) for i in sorted(added)),
            extra_data={'added_ids': sorted(added)},
        )

    if removed:
        log_action(
            request=request,
            entity_type=entity_type,
            entity_id=entity_id,
            action='m2m_remove',
            field_name=field_name,
            old_value=', '.join(_label(i) for i in sorted(removed)),
            extra_data={'removed_ids': sorted(removed)},
        )


