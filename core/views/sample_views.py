"""
CISIS — Views для работы с образцами.

Содержит:
- sample_create: создание образца
- sample_detail: детальная карточка образца
- _build_fields_data: формирование полей для шаблона
- _handle_status_change: обработка смены статуса
- _get_status_actions: доступные кнопки действий
- unfreeze_registration_block: AJAX разморозка блока регистрации
- search_protocols / search_standards / search_moisture_samples: AJAX endpoints

⭐ v3.15.0: Влагонасыщение (moisture conditioning)
  - accept_from_moisture в _handle_status_change
  - Автопереход MOISTURE_CONDITIONING после accept_sample (из мастерской)
  - Кнопка «💧 Принять из влагонасыщения» в _get_status_actions
  - moisture_conditioning / moisture_sample в _build_fields_data
  - Контекст moisture_sample + dependent_moisture_samples в sample_detail
  - Чекбокс + moisture_sample_id в sample_create
  - AJAX endpoint search_moisture_samples
"""

import logging
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.models import (
    Sample, Laboratory, Client, Contract,
    Standard, AccreditationArea, JournalColumn,
    SampleOperator, SampleStatus, WorkshopStatus,
    StandardLaboratory, StandardAccreditationArea,
    User, SampleStandard,
)
from core.permissions import PermissionChecker
from .constants import (
    AUTO_FIELDS, DATETIME_AUTO_FIELDS, STATUS_CHANGE_ACTIONS,
    REGISTRATION_FIELDS, WORKSHOP_FIELDS, TESTER_FIELDS,
    QMS_ROLES, WORKSHOP_ROLES, REPEAT_FIELD_GROUPS,
)
from .field_utils import (
    get_field_info, is_readonly_for_user, get_allowed_statuses_for_role,
    _validate_latin_only,
)
from .freeze_logic import _is_field_frozen, _can_unfreeze_block
from .save_logic import (
    save_sample_fields, handle_sample_save, _validate_trainee_for_draft,
)
from core.views.audit import log_action

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Проверка доступа
# ─────────────────────────────────────────────────────────────

def _check_sample_access(user, sample):
    """
    Проверяет доступ пользователя к образцу.
    Возвращает None если доступ разрешён, иначе строку с причиной отказа.
    """
    if user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD', 'SYSADMIN',
                     'QMS_HEAD', 'QMS_ADMIN', 'METROLOGIST', 'CTO', 'CEO'):
        return None

    if user.role == 'WORKSHOP_HEAD':
        if sample.manufacturing and sample.status != 'PENDING_VERIFICATION':
            return None
        return 'У вас нет доступа к этому образцу'

    if user.role == 'WORKSHOP':
        if not sample.workshop_status or sample.status == 'PENDING_VERIFICATION':
            return 'У вас нет доступа к этому образцу'
        return None

    if user.role == 'LAB_HEAD':
        if not user.laboratory:
            return 'У вас нет доступа к этому образцу'
        if user.has_laboratory(sample.laboratory):
            return None
        return 'У вас нет доступа к этому образцу'

    if not user.has_laboratory(sample.laboratory):
        return 'У вас нет доступа к этому образцу'

    return None


# ─────────────────────────────────────────────────────────────
# Обработка статусов
# ─────────────────────────────────────────────────────────────

def _handle_status_change(request, sample, action):
    """Обрабатывает изменение статуса образца по action."""
    if not PermissionChecker.can_edit(request.user, 'SAMPLES', 'status'):
        # Исключения: accept_sample и accept_from_moisture для регистраторов
        allow_without_permission = False
        if action == 'accept_sample' and request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD') and sample.status == 'TRANSFERRED':
            allow_without_permission = True
        if action == 'accept_from_moisture' and request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD') and sample.status in ('MOISTURE_CONDITIONING', 'MOISTURE_READY'):
            allow_without_permission = True
        if not allow_without_permission:
            messages.error(request, 'У вас нет прав на изменение статуса')
            return redirect('sample_detail', sample_id=sample.id)

    now = timezone.now()
    now_local_str = timezone.localtime(now).strftime('%H:%M')

    old_status = sample.status  # ⭐ v3.14.0: запоминаем для аудита

    if action in ('draft_ready', 'results_uploaded'):
        is_valid, error_msg = _validate_trainee_for_draft(sample)
        if not is_valid:
            messages.error(request, error_msg)
            return redirect('sample_detail', sample_id=sample.id)

    if action == 'complete_manufacturing':
        sample.status = SampleStatus.TRANSFERRED
        sample.workshop_status = WorkshopStatus.COMPLETED
        sample.manufacturing_completion_date = now
        sample.save()
        # ⭐ v3.14.0: аудит
        log_action(request, 'sample', sample.id, 'status_change',
                   field_name='status', old_value=old_status, new_value=sample.status)
        if sample.further_movement == 'TO_CLIENT_DEPT':
            messages.success(
                request,
                f'Изготовление завершено в {now_local_str}. '
                f'Образец ожидает приёмки специалистом по регистрации.'
            )
        else:
            messages.success(
                request,
                f'Изготовление завершено в {now_local_str}. '
                f'Образец передан в лабораторию и ожидает приёмки.'
            )
        return redirect('sample_detail', sample_id=sample.id)

    elif action == 'accept_sample':
        if sample.status != 'TRANSFERRED':
            messages.error(request, 'Образец не в статусе "Передан"')
            return redirect('sample_detail', sample_id=sample.id)
        if sample.further_movement == 'TO_CLIENT_DEPT':
            sample.status = SampleStatus.COMPLETED
            messages.success(request, f'Образец принят и завершён (нарезка)')
        else:
            sample.status = SampleStatus.REGISTERED
            messages.success(request, f'Образец принят в лабораторию в {now_local_str}')
        sample.save()
        # ⭐ v3.14.0: аудит
        log_action(request, 'sample', sample.id, 'status_change',
                   field_name='status', old_value=old_status, new_value=sample.status)

        # ⭐ v3.15.0: Автопереход в MOISTURE_CONDITIONING после приёма из мастерской
        if (sample.status == SampleStatus.REGISTERED
                and sample.moisture_conditioning
                and sample.moisture_sample_id):
            prev_status = sample.status
            sample.status = SampleStatus.MOISTURE_CONDITIONING
            sample.save()
            log_action(request, 'sample', sample.id, 'status_change',
                       field_name='status', old_value=prev_status,
                       new_value='MOISTURE_CONDITIONING')
            messages.info(
                request,
                'Образец автоматически переведён на влагонасыщение.'
            )

        return redirect('sample_detail', sample_id=sample.id)

    # ⭐ v3.15.0: Приём из влагонасыщения
    elif action == 'accept_from_moisture':
        if sample.status not in ('MOISTURE_CONDITIONING', 'MOISTURE_READY'):
            messages.error(request, 'Образец не в статусе влагонасыщения')
            return redirect('sample_detail', sample_id=sample.id)
        sample.status = SampleStatus.REGISTERED
        sample.save()
        log_action(request, 'sample', sample.id, 'status_change',
                   field_name='status', old_value=old_status, new_value=sample.status)
        messages.success(request, f'Образец принят из влагонасыщения в {now_local_str}')
        return redirect('sample_detail', sample_id=sample.id)

    elif action == 'complete_cutting_only':
        sample.status = SampleStatus.COMPLETED
        sample.save()
        # ⭐ v3.14.0: аудит
        log_action(request, 'sample', sample.id, 'status_change',
                   field_name='status', old_value=old_status, new_value=sample.status)
        messages.success(request, 'Нарезка завершена. Образец готов к выдаче заказчику.')
        return redirect('sample_detail', sample_id=sample.id)

    elif action == 'start_conditioning':
        old_cond_start = sample.conditioning_start_datetime  # ⭐ v3.16.0
        sample.status = 'CONDITIONING'
        sample.conditioning_start_datetime = now
        messages.success(request, f'Кондиционирование начато в {now_local_str}')

    elif action == 'ready_for_test':
        old_cond_end = sample.conditioning_end_datetime  # ⭐ v3.16.0
        sample.status = 'READY_FOR_TEST'
        sample.conditioning_end_datetime = now
        if sample.conditioning_start_datetime:
            duration = (now - sample.conditioning_start_datetime).total_seconds() / 3600
            messages.success(
                request,
                f'Кондиционирование завершено в {now_local_str}. '
                f'Длительность: {duration:.1f} часов'
            )
        else:
            messages.success(request, f'Кондиционирование завершено в {now_local_str}')

    elif action == 'start_testing':
        old_test_start = sample.testing_start_datetime  # ⭐ v3.16.0
        sample.status = 'IN_TESTING'
        sample.testing_start_datetime = now
        messages.success(request, f'Испытание начато в {now_local_str}')

    elif action == 'complete_test':
        old_test_end = sample.testing_end_datetime  # ⭐ v3.16.0
        sample.status = 'TESTED'
        sample.testing_end_datetime = now
        if sample.testing_start_datetime:
            duration = (now - sample.testing_start_datetime).total_seconds() / 3600
            messages.success(
                request,
                f'Испытание завершено в {now_local_str}. '
                f'Длительность: {duration:.1f} часов'
            )
        else:
            messages.success(request, f'Испытание завершено в {now_local_str}')

        # ⭐ v3.15.0: Автообновление зависимых образцов B при завершении испытания Образца A
        dependent_count = Sample.objects.filter(
            moisture_sample_id=sample.id,
            status='MOISTURE_CONDITIONING',
        ).update(status='MOISTURE_READY')
        if dependent_count:
            messages.info(
                request,
                f'Обновлено {dependent_count} связанных образцов → «Готово к передаче из УКИ»'
            )

    elif action == 'draft_ready':
        old_report_date = sample.report_prepared_date  # ⭐ v3.16.0
        old_report_by = sample.report_prepared_by_id  # ⭐ v3.16.0
        sample.status = 'DRAFT_READY'
        sample.report_prepared_date = now
        sample.report_prepared_by = request.user
        now_date_str = timezone.localtime(now).strftime('%d.%m.%Y %H:%M')
        messages.success(request, f'Черновик протокола готов. Дата подготовки: {now_date_str}')

    elif action == 'results_uploaded':
        old_report_date = sample.report_prepared_date  # ⭐ v3.16.0
        old_report_by = sample.report_prepared_by_id  # ⭐ v3.16.0
        sample.status = 'RESULTS_UPLOADED'
        sample.report_prepared_date = now
        sample.report_prepared_by = request.user
        now_date_str = timezone.localtime(now).strftime('%d.%m.%Y %H:%M')
        messages.success(request, f'Результаты выложены. Дата подготовки: {now_date_str}')

    elif action == 'protocol_issued':
        sample.status = 'PROTOCOL_ISSUED'
        messages.success(request, 'Статус изменён на "Протокол готов"')

    elif action == 'complete_sample':
        sample.status = 'COMPLETED'
        messages.success(request, 'Образец завершён')

    sample.save()

    # ⭐ v3.14.0: аудит (для всех веток, которые доходят до этого save)
    log_action(request, 'sample', sample.id, 'status_change',
               field_name='status', old_value=old_status, new_value=sample.status)

    # ⭐ v3.16.0: аудит автозаполненных datetime-полей
    if action == 'start_conditioning':
        log_action(request, 'sample', sample.id, 'update',
                   field_name='conditioning_start_datetime',
                   old_value=old_cond_start, new_value=now)
    elif action == 'ready_for_test':
        log_action(request, 'sample', sample.id, 'update',
                   field_name='conditioning_end_datetime',
                   old_value=old_cond_end, new_value=now)
    elif action == 'start_testing':
        log_action(request, 'sample', sample.id, 'update',
                   field_name='testing_start_datetime',
                   old_value=old_test_start, new_value=now)
    elif action == 'complete_test':
        log_action(request, 'sample', sample.id, 'update',
                   field_name='testing_end_datetime',
                   old_value=old_test_end, new_value=now)
    elif action in ('draft_ready', 'results_uploaded'):
        log_action(request, 'sample', sample.id, 'update',
                   field_name='report_prepared_date',
                   old_value=old_report_date, new_value=now)
        log_action(request, 'sample', sample.id, 'update',
                   field_name='report_prepared_by',
                   old_value=old_report_by, new_value=request.user.id)

    return redirect('sample_detail', sample_id=sample.id)


def _get_status_actions(user, sample):
    """Определяет доступные кнопки действий со статусом."""
    actions = []
    user_role = user.role

    if user_role == 'WORKSHOP_HEAD':
        if sample.status == 'MANUFACTURING':
            actions.append({
                'action': 'complete_manufacturing',
                'label': '✅ Завершить изготовление и передать',
                'class': 'btn-success',
                'new_status': 'TRANSFERRED',
            })
        return actions

    if user_role == 'WORKSHOP':
        if sample.status == 'MANUFACTURING':
            actions.append({
                'action': 'complete_manufacturing',
                'label': '✅ Завершить изготовление и передать',
                'class': 'btn-success',
                'new_status': 'TRANSFERRED',
            })
        return actions

    if user_role in ('TESTER','LAB_HEAD'):
        if sample.status == 'TRANSFERRED':
            is_own_lab = user.has_laboratory(sample.laboratory)
            if is_own_lab or user_role == 'LAB_HEAD':
                actions.append({
                    'action': 'accept_sample',
                    'label': '📥 Принять образец',
                    'class': 'btn-success',
                    'new_status': 'REGISTERED',
                })

        is_own_lab = user.has_laboratory(sample.laboratory)
        if not is_own_lab and user_role == 'LAB_HEAD':
            return actions

        working_statuses = (
            'REGISTERED', 'MANUFACTURED', 'TRANSFERRED', 'REPLACEMENT_PROTOCOL',
            'CONDITIONING', 'READY_FOR_TEST', 'IN_TESTING',
        )
        if sample.status in working_statuses:
            actions.extend([
                {
                    'action': 'start_conditioning',
                    'label': '🌡️ Начать кондиционирование',
                    'class': 'btn-primary',
                    'new_status': 'CONDITIONING',
                },
                {
                    'action': 'ready_for_test',
                    'label': '✓ Кондиционирование завершено',
                    'class': 'btn-success',
                    'new_status': 'READY_FOR_TEST',
                },
                {
                    'action': 'start_testing',
                    'label': '▶️ Начать испытание',
                    'class': 'btn-primary',
                    'new_status': 'IN_TESTING',
                },
                {
                    'action': 'complete_test',
                    'label': '✓ Завершить испытание',
                    'class': 'btn-warning',
                    'new_status': 'TESTED',
                },
            ])

        elif sample.status == 'TESTED':
            actions.extend([
                {
                    'action': 'draft_ready',
                    'label': '📝 Черновик протокола готов',
                    'class': 'btn-success',
                    'new_status': 'DRAFT_READY',
                },
                {
                    'action': 'results_uploaded',
                    'label': '📤 Результаты выложены (без протокола)',
                    'class': 'btn-warning',
                    'new_status': 'RESULTS_UPLOADED',
                },
            ])

    elif user_role in ('QMS_HEAD', 'QMS_ADMIN'):
        if sample.status == 'PROTOCOL_ISSUED':
            actions.append({
                'action': 'complete_sample',
                'label': '✅ Завершить работу (печать выполнена)',
                'class': 'btn-success',
                'new_status': 'COMPLETED',
            })

    if (user_role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD')
            and sample.status == 'TRANSFERRED'):
        actions.append({
            'action': 'accept_sample',
            'label': '📥 Принять образец',
            'class': 'btn-success',
            'new_status': 'REGISTERED',
        })

    # ⭐ v3.15.0: Приём из влагонасыщения
    # Кнопка доступна при MOISTURE_READY (автоматический переход)
    # или при MOISTURE_CONDITIONING если Образец A уже TESTED+
    if (user_role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD', 'LAB_HEAD', 'SYSADMIN')
            and sample.status in ('MOISTURE_CONDITIONING', 'MOISTURE_READY')):
        show_button = False
        if sample.status == 'MOISTURE_READY':
            # Образец A уже завершён — кнопка всегда доступна
            show_button = True
        elif sample.moisture_sample_id:
            # Проверяем статус Образца A вручную (на случай если автообновление не сработало)
            MOISTURE_READY_STATUSES = frozenset([
                'TESTED', 'DRAFT_READY', 'RESULTS_UPLOADED',
                'PROTOCOL_ISSUED', 'COMPLETED',
            ])
            moisture_sample_status = (
                Sample.objects.filter(id=sample.moisture_sample_id)
                .values_list('status', flat=True)
                .first()
            )
            show_button = (moisture_sample_status in MOISTURE_READY_STATUSES)
        else:
            # Без привязки — кнопка доступна (ручной режим)
            show_button = True

        if show_button:
            actions.append({
                'action': 'accept_from_moisture',
                'label': '💧 Принять из влагонасыщения',
                'class': 'btn-info',
                'new_status': 'REGISTERED',
            })

    if user.is_trainee:
        actions = [a for a in actions if a['action'] != 'protocol_issued']

    return actions


# ─────────────────────────────────────────────────────────────
# Построение данных для шаблона
# ─────────────────────────────────────────────────────────────

def _build_fields_data(request, sample):
    """Формирует структуру полей для отображения в шаблоне."""
    all_columns = JournalColumn.objects.filter(
        journal__code='SAMPLES', is_active=True
    ).order_by('display_order')

    field_groups = {
        'Регистрация': [
            'sequence_number', 'cipher', 'registration_date',
            'client', 'contract', 'contract_date', 'laboratory',
            'accompanying_doc_number', 'accompanying_doc_full_name',
            'accreditation_area', 'standards', 'test_code', 'test_type',
            'working_days', 'sample_received_date', 'object_info',
            'object_id', 'cutting_direction', 'test_conditions',
            'material', 'preparation',
            # ⭐ v3.20.0: manufacturing/moisture поля вынесены в кастомный блок шаблона
            # 'manufacturing', 'manufacturing_deadline', 'workshop_notes', 'further_movement',
            # 'cutting_standard', 'moisture_conditioning', 'moisture_sample',
            'determined_parameters',
            'sample_count', 'additional_sample_count',
            'notes', 'deadline',
            'report_type', 'pi_number',
            'uzk_required',
            'registered_by', 'verified_by', 'verified_at',
            'replacement_protocol_required', 'replacement_pi_number',
            'admin_notes',
        ],
        'Изготовление (Мастерская)': [
            'workshop_status',
            'manufacturing_completion_date',
            'manufacturing_measuring_instruments',
            'manufacturing_testing_equipment',
            'manufacturing_auxiliary_equipment',
            'manufacturing_operators',
        ],
        'Испытатель': [
            'conditioning_start_datetime',
            'conditioning_end_datetime',
            'testing_start_datetime',
            'testing_end_datetime',
            'report_prepared_date',
            'report_prepared_by',
            'operator_notes',
            'measuring_instruments',
            'testing_equipment',
            'auxiliary_equipment',
            'operators',
        ],
        'СМК': [
            'protocol_checked_by',
            'protocol_issued_date',
            'protocol_printed_date',
            'replacement_protocol_issued_date',
        ],
        'Статусы': [
            'status',
        ],
    }

    user = request.user

    # Мастерская и WORKSHOP_HEAD не видят поле status
    if user.role in WORKSHOP_ROLES:
        for group_name in field_groups:
            field_groups[group_name] = [
                f for f in field_groups[group_name] if f != 'status'
            ]

    fields_data = {}
    for group_name, field_codes in field_groups.items():
        group_fields = []

        for field_code in field_codes:
            column = all_columns.filter(code=field_code).first()
            if not column:
                continue

            permission = PermissionChecker.get_user_permission(user, 'SAMPLES', field_code)
            if permission == 'NONE':
                continue

            field_info = get_field_info(sample, field_code, user)

            is_editable = False
            frozen_reason = None

            if field_code == 'status':
                if user.role in ('TESTER', 'OPERATOR') or user.role in WORKSHOP_ROLES:
                    continue
                is_editable = (permission == 'EDIT')

                if user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD'):
                    unfrozen_key = f'unfrozen_registration_{sample.id}'
                    if sample.status != 'PENDING_VERIFICATION' and request.session.get(unfrozen_key, False):
                        is_editable = True
                        allowed_after_unfreeze = {'CANCELLED', 'PENDING_VERIFICATION', sample.status}
                        field_info['choices'] = [
                            (k, v) for k, v in (field_info.get('choices') or [])
                            if k in allowed_after_unfreeze
                        ]
                    elif sample.status != 'PENDING_VERIFICATION':
                        is_editable = False

            elif field_code in AUTO_FIELDS:
                is_editable = False

            elif field_code in DATETIME_AUTO_FIELDS:
                is_editable = (
                    permission == 'EDIT'
                    and user.role in ('SYSADMIN', 'LAB_HEAD', 'QMS_HEAD', 'QMS_ADMIN', 'WORKSHOP_HEAD')
                )

            else:
                is_editable = (permission == 'EDIT')

            if is_editable:
                is_frozen, reason = _is_field_frozen(field_code, user, sample, request=request)
                if is_frozen:
                    is_editable = False
                    frozen_reason = reason

            group_fields.append({
                'code': field_code,
                'name': column.name,
                'value': field_info['value'],
                'display_value': field_info['display_value'],
                'field_type': field_info['field_type'],
                'choices': field_info.get('choices'),
                'options': field_info.get('options'),
                'is_editable': is_editable,
                'is_auto': field_code in AUTO_FIELDS or field_code in DATETIME_AUTO_FIELDS,
                'is_frozen': frozen_reason is not None,
                'frozen_reason': frozen_reason,
                'permission': permission,
                'help_text': field_info.get('help_text'),
            })

        if group_fields:
            fields_data[group_name] = group_fields

    return fields_data


# ─────────────────────────────────────────────────────────────
# Verification contexts
# ─────────────────────────────────────────────────────────────

def _get_verification_context(request, sample):
    """Формирует контекст для блока проверки регистрации."""
    can_verify = False
    verification_message = ''
    verification_info = None

    if sample.status == 'PENDING_VERIFICATION':
        if sample.registered_by != request.user:
            if request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD', 'SYSADMIN'):
                can_verify = True
                verification_message = (
                    f'Образец зарегистрирован {sample.registered_by.full_name}. '
                    f'Вы можете проверить и подтвердить регистрацию.'
                )
            elif (request.user.role == 'LAB_HEAD'
                  and request.user.has_laboratory(sample.laboratory)):
                can_verify = True
                verification_message = (
                    f'Образец зарегистрирован {sample.registered_by.full_name}. '
                    f'Вы можете проверить и подтвердить регистрацию.'
                )
            else:
                verification_message = 'Образец ожидает проверки.'
        else:
            verification_message = (
                'Вы зарегистрировали этот образец. '
                'Проверку должен выполнить другой сотрудник.'
            )

    if sample.verified_by:
        verification_info = {
            'verified_by': sample.verified_by.full_name,
            'verified_at': sample.verified_at,
            'registered_by': sample.registered_by.full_name,
        }

    return can_verify, verification_message, verification_info


def _get_protocol_verification_context(request, sample):
    """Формирует контекст для блока проверки протокола."""
    can_verify_protocol = False
    message = ''
    info = None

    if sample.status in ('DRAFT_READY', 'RESULTS_UPLOADED'):
        can_check = False

        if request.user.role in ('QMS_HEAD', 'QMS_ADMIN', 'SYSADMIN'):
            can_check = True
        elif (request.user.role == 'LAB_HEAD'
              and request.user.has_laboratory(sample.laboratory)):
            can_check = True

        if can_check:
            can_verify_protocol = True
            if sample.status == 'DRAFT_READY':
                message = (
                    f'Черновик протокола готов. Проверьте и подтвердите '
                    f'выпуск протокола {sample.pi_number}.'
                )
            else:
                message = (
                    'Результаты испытаний выложены. '
                    'Проверьте и подтвердите завершение работы.'
                )
        else:
            if sample.status == 'DRAFT_READY':
                message = 'Черновик протокола ожидает проверки.'
            else:
                message = 'Результаты ожидают проверки.'

    if sample.protocol_checked_by:
        info = {
            'checked_by': sample.protocol_checked_by.full_name,
            'checked_at': sample.protocol_checked_at,
            'issued_date': sample.protocol_issued_date,
            'pi_number': sample.pi_number,
        }

    return can_verify_protocol, message, info


# ─────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────

@login_required
def sample_create(request):
    """Создание нового образца."""

    allowed_roles = ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD', 'LAB_HEAD', 'SYSADMIN')
    if request.user.role not in allowed_roles:
        messages.error(request, 'У вас нет прав на создание образцов')
        return redirect('journal_samples')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                sample = Sample()

                sample.laboratory_id = request.POST.get('laboratory')
                sample.client_id = request.POST.get('client')
                sample.accompanying_doc_number = request.POST.get('accompanying_doc_number', '')
                sample.accreditation_area_id = request.POST.get('accreditation_area')
                #   (ничего — стандарты добавляются ПОСЛЕ save, см. ниже)
                sample.working_days = int(request.POST.get('working_days', 10))
                sample.determined_parameters = request.POST.get('determined_parameters', '')
                sample.preparation = request.POST.get('preparation', '')
                sample.notes = request.POST.get('notes', '')
                sample.workshop_notes = request.POST.get('workshop_notes', '')
                sample.admin_notes = request.POST.get('admin_notes', '')
                sample.sample_count = int(request.POST.get('sample_count', 1))
                sample.additional_sample_count = int(request.POST.get('additional_sample_count', 0))
                sample.registered_by = request.user

                contract_id = request.POST.get('contract')
                if contract_id:
                    sample.contract_id = contract_id
                    contract = Contract.objects.get(id=contract_id)
                    sample.contract_date = contract.date

                    # ⭐ v3.19.0: Акт приёма-передачи
                acceptance_act_id = request.POST.get('acceptance_act')
                if acceptance_act_id:
                    sample.acceptance_act_id = int(acceptance_act_id)

                sample_received_date_str = request.POST.get('sample_received_date')
                if sample_received_date_str:
                    sample.sample_received_date = datetime.strptime(
                        sample_received_date_str, '%Y-%m-%d'
                    ).date()
                else:
                    sample.sample_received_date = timezone.now().date()

                sample.registration_date = timezone.now().date()
                sample.object_info = request.POST.get('object_info', '')

                object_id_value = request.POST.get('object_id', '')
                is_valid, error_msg = _validate_latin_only('object_id', object_id_value)
                if not is_valid:
                    messages.error(request, f'ID объекта испытаний: {error_msg}')
                    return redirect('sample_create')
                sample.object_id = object_id_value

                sample.cutting_direction = request.POST.get('cutting_direction', '')
                sample.test_conditions = request.POST.get('test_conditions', '')
                sample.material = request.POST.get('material', '')

                sample.manufacturing = request.POST.get('manufacturing') == 'on'
                sample.uzk_required = request.POST.get('uzk_required') == 'on'

                # ⭐ v3.15.0: Стандарт на нарезку
                cutting_standard_id = request.POST.get('cutting_standard')
                if cutting_standard_id:
                    sample.cutting_standard_id = int(cutting_standard_id)

                # ⭐ v3.15.0: Влагонасыщение
                sample.moisture_conditioning = request.POST.get('moisture_conditioning') == 'on'
                moisture_sample_id = request.POST.get('moisture_sample_id')
                if sample.moisture_conditioning and moisture_sample_id:
                    sample.moisture_sample_id = int(moisture_sample_id)
                else:
                    sample.moisture_sample_id = None

                sample.replacement_protocol_required = (
                    request.POST.get('replacement_protocol_required') == 'on'
                )

                sample.workshop_status = (
                    WorkshopStatus.IN_WORKSHOP if sample.manufacturing else None
                )

                sample.report_type = request.POST.get('report_type', 'PROTOCOL')
                existing_pi = request.POST.get('existing_pi_number', '').strip()
                if existing_pi and sample.report_type != 'WITHOUT_REPORT':
                    if Sample.objects.filter(pi_number=existing_pi).exists():
                        sample._use_existing_pi_number = existing_pi
                    else:
                        messages.warning(
                            request,
                            f'Указанный номер протокола «{existing_pi}» не найден. '
                            f'Будет сгенерирован новый номер.'
                        )
                manufacturing_deadline_str = request.POST.get('manufacturing_deadline')
                if manufacturing_deadline_str:
                    sample.manufacturing_deadline = datetime.strptime(
                        manufacturing_deadline_str, '%Y-%m-%d'
                    ).date()
                sample.further_movement = request.POST.get('further_movement', '')

                status_choice = request.POST.get('status', 'PENDING_VERIFICATION')
                sample.status = (
                    'CANCELLED' if status_choice == 'CANCELLED'
                    else 'PENDING_VERIFICATION'
                )

                sample.save()

                # ⭐ v3.13.0: Добавляем стандарты (M2M — после save)
                standard_ids = request.POST.getlist('standards')
                for std_id in standard_ids:
                    if std_id:
                        SampleStandard.objects.create(
                            sample=sample, standard_id=int(std_id)
                        )

                # Копируем test_code/test_type из первого стандарта
                if standard_ids:
                    first_std = Standard.objects.filter(id=int(standard_ids[0])).first()
                    if first_std:
                        sample.test_code = first_std.test_code
                        sample.test_type = first_std.test_type
                        sample.cipher = sample.generate_cipher()
                        if (sample.report_type != 'WITHOUT_REPORT'
                                and not getattr(sample, '_use_existing_pi_number', None)):
                            sample.pi_number = sample.generate_pi_number()
                        sample.save()

                log_action(request, 'sample', sample.id, 'create', extra_data={
                    'cipher': sample.cipher,
                })

                if sample.status == 'PENDING_VERIFICATION':
                    messages.success(
                        request,
                        f'Образец {sample.cipher} создан (№ {sample.sequence_number}). '
                        f'Ожидает проверки.'
                    )
                else:
                    messages.warning(
                        request,
                        f'Образец {sample.cipher} создан со статусом "Отменено"'
                    )

                # «Создать + такой же»
                is_repeat = request.POST.get('action') == 'create_and_repeat'
                if is_repeat:
                    selected_groups = request.POST.getlist('repeat_groups')
                    if selected_groups:
                        prefs = request.user.ui_preferences or {}
                        prefs['repeat_sample_groups'] = selected_groups
                        request.user.ui_preferences = prefs
                        request.user.save(update_fields=['ui_preferences'])

                    all_sample_data = {
                        'laboratory': sample.laboratory_id,
                        'client': sample.client_id,
                        'contract': sample.contract_id if sample.contract_id else '',
                        'working_days': sample.working_days,
                        'accompanying_doc_number': sample.accompanying_doc_number or '',
                        'acceptance_act': sample.acceptance_act or '',
                        'accreditation_area': sample.accreditation_area_id,
                        'standards': list(SampleStandard.objects.filter(sample=sample).values_list('standard_id', flat=True)),
                        'report_type': sample.report_type or 'PROTOCOL',
                        'determined_parameters': sample.determined_parameters or '',
                        'sample_count': sample.sample_count,
                        'additional_sample_count': sample.additional_sample_count,
                        'object_id': sample.object_id or '',
                        'cutting_direction': sample.cutting_direction or '',
                        'test_conditions': sample.test_conditions or '',
                        'material': sample.material or '',
                        'preparation': sample.preparation or '',
                        'notes': sample.notes or '',
                        'object_info': sample.object_info or '',
                        'workshop_notes': sample.workshop_notes or '',
                        'admin_notes': sample.admin_notes or '',
                        'manufacturing': sample.manufacturing,
                        'moisture_conditioning': sample.moisture_conditioning,  # ⭐ v3.15.0
                        'further_movement': sample.further_movement or '',
                    }

                    repeat_data = {}
                    for group_code in selected_groups:
                        group = REPEAT_FIELD_GROUPS.get(group_code)
                        if group:
                            for field in group['fields']:
                                if field in all_sample_data:
                                    repeat_data[field] = all_sample_data[field]

                    warn_fields = []
                    for group_code in selected_groups:
                        group = REPEAT_FIELD_GROUPS.get(group_code)
                        if group and group.get('warn'):
                            warn_fields.extend(group['fields'])
                    if warn_fields:
                        repeat_data['_warn_fields'] = warn_fields

                    request.session['last_sample_data'] = repeat_data
                    return redirect('sample_create')
                else:
                    if 'last_sample_data' in request.session:
                        del request.session['last_sample_data']
                    return redirect('sample_detail', sample_id=sample.id)

        except Exception as e:
            logger.exception('Ошибка при создании образца')
            messages.error(request, f'Ошибка при создании образца: {e}')
            return redirect('sample_create')

    # ─── GET: показываем форму ───
    laboratories = Laboratory.objects.filter(is_active=True, department_type='LAB').order_by('name')
    clients = Client.objects.filter(is_active=True).order_by('name')
    accreditation_areas = AccreditationArea.objects.filter(is_active=True).order_by('name')
    standards = Standard.objects.filter(is_active=True).order_by('code')

    last_data = request.session.pop('last_sample_data', {})

    for key in ('laboratory', 'client', 'contract', 'accreditation_area'):
        if key in last_data and last_data[key]:
            try:
                last_data[key] = int(last_data[key])
            except (ValueError, TypeError):
                pass
        if 'standards' in last_data and last_data['standards']:
            try:
                last_data['standards'] = [int(x) for x in last_data['standards']]
            except (ValueError, TypeError):
                pass

    contracts = []
    if last_data.get('client'):
        contracts = Contract.objects.filter(
            client_id=last_data['client'], status='ACTIVE'
        ).order_by('-date')

    prefs = request.user.ui_preferences or {}
    saved_repeat_groups = prefs.get('repeat_sample_groups', ['basic', 'doc', 'testing'])

    return render(request, 'core/sample_create.html', {
        'laboratories': laboratories,
        'clients': clients,
        'accreditation_areas': accreditation_areas,
        'standards': standards,
        'contracts': contracts,
        'last_data': last_data,
        'warn_fields': last_data.get('_warn_fields', []),
        'user': request.user,
        'current_user_fullname': request.user.full_name,
        'repeat_field_groups': REPEAT_FIELD_GROUPS,
        'saved_repeat_groups': saved_repeat_groups,
    })


@login_required
def sample_detail(request, sample_id):
    """Просмотр и редактирование образца."""

    sample = get_object_or_404(
        Sample.objects.select_related(
            'laboratory', 'client', 'contract',
            'accreditation_area', 'registered_by', 'report_prepared_by',
            'protocol_checked_by', 'verified_by',
            'moisture_sample', 'cutting_standard',  # ⭐ v3.15.0
        ).prefetch_related(
            'measuring_instruments', 'testing_equipment', 'operators',
            'standards',
        ),
        id=sample_id
    )

    if not PermissionChecker.has_journal_access(request.user, 'SAMPLES'):
        messages.error(request, 'У вас нет доступа к журналу образцов')
        return redirect('workspace_home')

    access_error = _check_sample_access(request.user, sample)
    if access_error:
        messages.error(request, access_error)
        return redirect('journal_samples')

    # --- POST ---
    if request.method == 'POST':
        action = request.POST.get('action')

        if action in STATUS_CHANGE_ACTIONS:
            try:
                with transaction.atomic():
                    updated_fields = save_sample_fields(request, sample)
                    if updated_fields:
                        messages.info(
                            request,
                            f'Сохранены изменения: {", ".join(updated_fields)}'
                        )
            except Exception as e:
                logger.exception('Ошибка при сохранении полей перед сменой статуса')
                messages.error(request, f'Ошибка при сохранении полей: {e}')
                return redirect('sample_detail', sample_id=sample.id)

        if action == 'save':
            return handle_sample_save(request, sample)
        elif action in STATUS_CHANGE_ACTIONS:
            return _handle_status_change(request, sample, action)

    # --- GET: формирование контекста ---
    fields_data = _build_fields_data(request, sample)

    can_edit_any = any(
        field['is_editable']
        for group in fields_data.values()
        for field in group
    )

    can_change_status = PermissionChecker.can_edit(request.user, 'SAMPLES', 'status')
    status_actions = _get_status_actions(request.user, sample)

    can_verify, verification_message, verification_info = (
        _get_verification_context(request, sample)
    )

    can_verify_protocol, protocol_verification_message, protocol_verification_info = (
        _get_protocol_verification_context(request, sample)
    )

    sample_files = sample.files.all().order_by('-uploaded_at')
    can_upload_files = PermissionChecker.can_edit(request.user, 'SAMPLES', 'files_path')
    can_delete_files = request.user.role in (
        'CLIENT_MANAGER', 'CLIENT_DEPT_HEAD',
        'LAB_HEAD', 'QMS_HEAD', 'QMS_ADMIN',
        'SYSADMIN',
        'WORKSHOP_HEAD', 'WORKSHOP',
    )

    freezing_actions = []
    for act in status_actions:
        if act['action'] in ('draft_ready', 'results_uploaded'):
            freezing_actions.append(act['action'])
        elif act['action'] == 'complete_manufacturing':
            freezing_actions.append(act['action'])

    is_workshop_head_view = (
        request.user.role in WORKSHOP_ROLES
        and not request.user.has_laboratory(sample.laboratory)
    )

    # Контекст разморозки блока регистрации
    registration_is_frozen = (sample.status != 'PENDING_VERIFICATION')
    unfrozen_key = f'unfrozen_registration_{sample.id}'
    registration_unfrozen = request.session.get(unfrozen_key, False)
    can_unfreeze_registration = (
        registration_is_frozen
        and not registration_unfrozen
        and _can_unfreeze_block(request.user, sample, 'registration')
        and request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD')
    )

    # ⭐ v3.14.0: Доступ к журналу аудита
    can_view_audit = request.user.role in (
        'SYSADMIN', 'QMS_HEAD', 'QMS_ADMIN', 'CTO', 'CEO',
        'CLIENT_DEPT_HEAD', 'LAB_HEAD', 'WORKSHOP_HEAD',
    )

    # ⭐ v3.15.0: Контекст влагонасыщения
    moisture_sample = None
    moisture_sample_ready = False
    can_view_moisture_sample = False
    if sample.moisture_sample_id:
        moisture_sample = sample.moisture_sample  # уже в select_related

        # Автопереход: если Образец A достиг TESTED+ — перевести Образец B
        # из MOISTURE_CONDITIONING в MOISTURE_READY
        MOISTURE_DONE_STATUSES = frozenset([
            'TESTED', 'DRAFT_READY', 'RESULTS_UPLOADED',
            'PROTOCOL_ISSUED', 'COMPLETED',
        ])
        if (sample.status == 'MOISTURE_CONDITIONING'
                and moisture_sample.status in MOISTURE_DONE_STATUSES):
            sample.status = 'MOISTURE_READY'
            sample.save(update_fields=['status', 'updated_at'])
            log_action(request, 'sample', sample.id, 'status_change',
                       field_name='status',
                       old_value='MOISTURE_CONDITIONING',
                       new_value='MOISTURE_READY')

        moisture_sample_ready = (
            sample.status == 'MOISTURE_READY'
            or moisture_sample.status in MOISTURE_DONE_STATUSES
        )
        # Проверяем, есть ли у пользователя доступ к образцу УКИ
        if request.user.role in ('WORKSHOP', 'WORKSHOP_HEAD'):
            can_view_moisture_sample = False
        else:
            can_view_moisture_sample = (_check_sample_access(request.user, moisture_sample) is None)

    # Обратная связь: образцы, привязанные к данному (если это Образец A)
    dependent_moisture_samples = Sample.objects.filter(
        moisture_sample_id=sample.id
    ).select_related('laboratory').only(
        'id', 'cipher', 'sequence_number', 'status', 'laboratory'
    )

    # Проверяем доступ к каждому зависимому образцу
    for dep in dependent_moisture_samples:
        # Мастерская не должна видеть ссылки на образцы других лабораторий
        if request.user.role in ('WORKSHOP', 'WORKSHOP_HEAD'):
            dep.is_accessible = False
        else:
            dep.is_accessible = (_check_sample_access(request.user, dep) is None)

    _mfg_perm = PermissionChecker.get_user_permission(request.user, 'SAMPLES', 'manufacturing')
    _mfg_frozen, _ = _is_field_frozen('manufacturing', request.user, sample, request=request)
    can_edit_manufacturing = (_mfg_perm == 'EDIT' and not _mfg_frozen)

    _mc_perm = PermissionChecker.get_user_permission(request.user, 'SAMPLES', 'moisture_conditioning')
    _mc_frozen, _ = _is_field_frozen('moisture_conditioning', request.user, sample, request=request)
    can_edit_moisture = (_mc_perm == 'EDIT' and not _mc_frozen)

    show_manufacturing_block = _mfg_perm in ('VIEW', 'EDIT')
    show_moisture_block = _mc_perm in ('VIEW', 'EDIT')

    return render(request, 'core/sample_detail.html', {
        'sample': sample,
        'fields_data': fields_data,
        'can_edit_any': can_edit_any,
        'can_change_status': can_change_status,
        'status_actions': status_actions,
        'freezing_actions': freezing_actions,
        'is_workshop_head_view': is_workshop_head_view,
        'can_unfreeze_registration': can_unfreeze_registration,
        'registration_unfrozen': registration_unfrozen,
        'sample_files': sample_files,
        'can_upload_files': can_upload_files,
        'can_delete_files': can_delete_files,
        'can_verify': can_verify,
        'verification_message': verification_message,
        'verification_info': verification_info,
        'can_verify_protocol': can_verify_protocol,
        'protocol_verification_message': protocol_verification_message,
        'protocol_verification_info': protocol_verification_info,
        'can_view_audit': can_view_audit,
        'moisture_sample': moisture_sample,
        'moisture_sample_ready': moisture_sample_ready,
        'can_view_moisture_sample': can_view_moisture_sample,
        'dependent_moisture_samples': dependent_moisture_samples,
        'can_edit_manufacturing': can_edit_manufacturing,  # ⭐ v3.20.0
        'can_edit_moisture': can_edit_moisture,  # ⭐ v3.20.0
        'show_manufacturing_block': show_manufacturing_block,  # ⭐ v3.20.0
        'show_moisture_block': show_moisture_block,  # ⭐ v3.20.0
    })

# ─────────────────────────────────────────────────────────────
# AJAX endpoints
# ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def unfreeze_registration_block(request, sample_id):
    """
    AJAX endpoint — разморозка блока регистрации.
    POST /workspace/samples/<id>/unfreeze-registration/
    """
    sample = get_object_or_404(Sample, id=sample_id)
    user = request.user

    access_error = _check_sample_access(user, sample)
    if access_error:
        return JsonResponse({'error': access_error}, status=403)

    if not _can_unfreeze_block(user, sample, 'registration'):
        return JsonResponse({'error': 'Нет прав на разморозку блока регистрации'}, status=403)

    if sample.status == 'PENDING_VERIFICATION':
        return JsonResponse({'error': 'Блок регистрации не заморожен'}, status=400)

    now = timezone.now()
    now_str = timezone.localtime(now).strftime('%d.%m.%Y %H:%M')
    unfreeze_note = (
        f"[{now_str}] 🔓 Разморозка блока регистрации — "
        f"{user.full_name} ({user.role})"
    )

    if sample.admin_notes:
        sample.admin_notes = f"{sample.admin_notes}\n{unfreeze_note}"
    else:
        sample.admin_notes = unfreeze_note

    sample.save(update_fields=['admin_notes', 'updated_at'])

    unfrozen_key = f'unfrozen_registration_{sample.id}'
    request.session[unfrozen_key] = True
    request.session.modified = True

    return JsonResponse({
        'success': True,
        'message': 'Блок регистрации разморожен',
    })


@login_required
def search_protocols(request):
    """
    AJAX endpoint: поиск существующих номеров протоколов.
    GET: ?laboratory=ID&client=ID&q=search&limit=10
    """
    laboratory_id = request.GET.get('laboratory')
    if not laboratory_id:
        return JsonResponse({'protocols': []})

    qs = Sample.objects.filter(
        laboratory_id=laboratory_id,
        report_type='PROTOCOL',
    ).exclude(
        pi_number=''
    ).exclude(
        pi_number__isnull=True
    )

    client_id = request.GET.get('client')
    if client_id:
        qs = qs.filter(client_id=client_id)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(pi_number__icontains=q)

    limit = int(request.GET.get('limit', 10))
    protocols = (
        qs.values('pi_number')
        .annotate(
            last_date=models.Max('registration_date'),
            sample_count=models.Count('id'),
        )
        .order_by('-last_date')[:limit]
    )

    return JsonResponse({
        'protocols': [
            {
                'pi_number': p['pi_number'],
                'sample_count': p['sample_count'],
            }
            for p in protocols
        ]
    })


@login_required
def search_standards(request):
    """
    AJAX endpoint: стандарты, отфильтрованные по лаборатории и/или области.
    GET: ?laboratory=ID&accreditation_area=ID
    """
    qs = Standard.objects.filter(is_active=True)

    laboratory_id = request.GET.get('laboratory')
    accreditation_area_id = request.GET.get('accreditation_area')

    if laboratory_id:
        standard_ids = StandardLaboratory.objects.filter(
            laboratory_id=laboratory_id
        ).values_list('standard_id', flat=True)
        qs = qs.filter(id__in=standard_ids)

    if accreditation_area_id:
        standard_ids = StandardAccreditationArea.objects.filter(
            accreditation_area_id=accreditation_area_id
        ).values_list('standard_id', flat=True)
        qs = qs.filter(id__in=standard_ids)

    standards = qs.order_by('code').values('id', 'code', 'name', 'test_code', 'test_type')

    return JsonResponse({'standards': list(standards)})


@login_required
def search_moisture_samples(request):
    """
    ⭐ v3.15.0: AJAX endpoint — поиск образцов УКИ для привязки влагонасыщения.
    GET: ?q=search_query&limit=10
    Возвращает образцы лаборатории ACT (УКИ), кроме отменённых.
    """
    q = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))

    # Находим лабораторию УКИ (code='ACT')
    act_lab = Laboratory.objects.filter(code='ACT').first()
    if not act_lab:
        return JsonResponse({'samples': []})

    qs = Sample.objects.filter(
        laboratory=act_lab,
    ).exclude(
        status='CANCELLED',
    ).select_related('laboratory')

    if q:
        qs = qs.filter(
            models.Q(cipher__icontains=q) |
            models.Q(sequence_number__icontains=q)
        )

    samples = qs.order_by('-registration_date', '-sequence_number')[:limit]

    return JsonResponse({
        'samples': [
            {
                'id': s.id,
                'cipher': s.cipher,
                'sequence_number': s.sequence_number,
                'status': s.get_status_display(),
                'status_code': s.status,
            }
            for s in samples
        ]
    })
@login_required
def api_check_operator_accreditation(request):
    """
    ⭐ v3.28.0: AJAX — проверка допуска операторов к областям аккредитации.

    GET: ?operator_ids=1,2,3&standard_ids=4,5,6
    Возвращает JSON со списком предупреждений.

    Учитывает:
    - user_accreditation_areas (допуск к области)
    - user_standard_exclusions (исключения по конкретным стандартам)
    """
    operator_ids_raw = request.GET.get('operator_ids', '')
    standard_ids_raw = request.GET.get('standard_ids', '')

    if not operator_ids_raw or not standard_ids_raw:
        return JsonResponse({'warnings': []})

    try:
        operator_ids = [int(x) for x in operator_ids_raw.split(',') if x.strip()]
        standard_ids = [int(x) for x in standard_ids_raw.split(',') if x.strip()]
    except (ValueError, TypeError):
        return JsonResponse({'warnings': []})

    if not operator_ids or not standard_ids:
        return JsonResponse({'warnings': []})

    from django.db import connection

    # 1. Для каждого стандарта — его НЕ-дефолтные области
    with connection.cursor() as cur:
        cur.execute("""
            SELECT saa.standard_id, aa.id AS area_id, aa.name AS area_name
            FROM standard_accreditation_areas saa
            JOIN accreditation_areas aa ON aa.id = saa.accreditation_area_id
            WHERE saa.standard_id = ANY(%s)
              AND aa.is_default = FALSE
              AND aa.is_active = TRUE
        """, [standard_ids])
        # {standard_id: {area_id: area_name, ...}}
        standard_areas = {}
        for row in cur.fetchall():
            standard_areas.setdefault(row[0], {})[row[1]] = row[2]

    # Если все стандарты только «Вне области» — проверка не нужна
    if not standard_areas:
        return JsonResponse({'warnings': []})

    # 2. Допуски операторов к областям
    all_area_ids = set()
    for areas in standard_areas.values():
        all_area_ids.update(areas.keys())

    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, accreditation_area_id
            FROM user_accreditation_areas
            WHERE user_id = ANY(%s)
              AND accreditation_area_id = ANY(%s)
        """, [operator_ids, list(all_area_ids)])
        # set of (user_id, area_id)
        operator_area_set = {(row[0], row[1]) for row in cur.fetchall()}

    # 3. Исключения по стандартам
    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, standard_id
            FROM user_standard_exclusions
            WHERE user_id = ANY(%s)
              AND standard_id = ANY(%s)
        """, [operator_ids, list(standard_areas.keys())])
        # set of (user_id, standard_id)
        exclusion_set = {(row[0], row[1]) for row in cur.fetchall()}

    # 4. Имена операторов
    operators = User.objects.filter(id__in=operator_ids).values(
        'id', 'last_name', 'first_name', 'sur_name'
    )
    operator_names = {}
    for op in operators:
        name = f"{op['last_name']} {op['first_name']}"
        if op.get('sur_name'):
            name += f" {op['sur_name']}"
        operator_names[op['id']] = name

    # 5. Формируем предупреждения
    warnings = []
    for op_id in operator_ids:
        issues = []  # [(standard_code, reason), ...]

        for std_id, areas in standard_areas.items():
            # Проверяем исключение по стандарту
            if (op_id, std_id) in exclusion_set:
                issues.append({
                    'standard_id': std_id,
                    'reason': 'excluded',  # исключён из допуска
                })
                continue

            # Проверяем допуск к хотя бы одной области этого стандарта
            has_area = any(
                (op_id, area_id) in operator_area_set
                for area_id in areas.keys()
            )
            if not has_area:
                area_names = list(areas.values())
                issues.append({
                    'standard_id': std_id,
                    'reason': 'no_area',
                    'missing_areas': area_names,
                })

        if issues:
            # Получаем коды стандартов для отображения
            std_codes = dict(
                Standard.objects.filter(id__in=[i['standard_id'] for i in issues])
                .values_list('id', 'code')
            )

            details = []
            for issue in issues:
                std_code = std_codes.get(issue['standard_id'], f"ID {issue['standard_id']}")
                if issue['reason'] == 'excluded':
                    details.append(f'{std_code} (исключён)')
                else:
                    areas_str = ', '.join(issue['missing_areas'])
                    details.append(f'{std_code} (нет допуска: {areas_str})')

            warnings.append({
                'operator_id': op_id,
                'operator_name': operator_names.get(op_id, f'ID {op_id}'),
                'details': details,
            })

    return JsonResponse({'warnings': warnings})