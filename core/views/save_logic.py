"""
CISIS — Логика сохранения полей образца.

Содержит:
- save_sample_fields: сохранение изменённых полей из POST
- handle_sample_save: обёртка с transaction + messages
- handle_m2m_update: обновление M2M-связей
- _recalculate_auto_fields: пересчёт зависимых полей
- _parse_datetime_value: парсинг datetime из формы
- _validate_trainee_for_draft: валидация стажёров
- _handle_manufacturing_toggle: включение/отключение нарезки ⭐ v3.20.0
- _handle_moisture_toggle: включение/отключение влагонасыщения ⭐ v3.20.0
"""

import logging
from datetime import datetime

from django.db import models, transaction
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.timezone import make_aware
from django.core.exceptions import FieldDoesNotExist

from core.models import (
    Sample, JournalColumn, WorkshopStatus, User,
    SampleMeasuringInstrument, SampleTestingEquipment, SampleOperator,
    SampleManufacturingMeasuringInstrument,
    SampleManufacturingTestingEquipment,
    SampleManufacturingOperator,
    SampleManufacturingAuxiliaryEquipment,
    SampleAuxiliaryEquipment,SampleStandard,
)
from core.permissions import PermissionChecker
from .constants import (
    AUTO_FIELDS, AUTO_FIELD_DEPENDENCIES,
    LATIN_ONLY_FIELDS, LATIN_ONLY_IF_MI,
)
from .field_utils import _validate_latin_only
from .freeze_logic import _is_field_frozen
from core.views.audit import log_action, log_field_changes, log_m2m_changes
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# ⭐ v3.20.0: Обработка включения/отключения нарезки и влагонасыщения
# ─────────────────────────────────────────────────────────────

def _handle_manufacturing_toggle(request, sample, old_value, new_value, audit_old_values):
    """
    ⭐ v3.20.0: Обрабатывает включение/отключение нарезки на уже существующем образце.

    Включение (False → True):
      - workshop_status = IN_WORKSHOP
      - manufacturing_deadline пересчитывается (если не задан вручную в форме)
      - panel_id автогенерируется (в save())

    Отключение (True → False):
      - workshop_status = None
      - manufacturing_deadline = None
      - further_movement = ''
      - cutting_standard = None

    Статус образца НЕ меняется автоматически.
    """
    extra_updated = []

    if new_value and not old_value:
        # ─── Включение нарезки ───
        old_ws = sample.workshop_status
        sample.workshop_status = WorkshopStatus.IN_WORKSHOP
        if old_ws != WorkshopStatus.IN_WORKSHOP:
            audit_old_values['workshop_status'] = (old_ws, WorkshopStatus.IN_WORKSHOP)
            extra_updated.append('Статус мастерской')

    elif old_value and not new_value:
        # ─── Отключение нарезки ───
        # workshop_status → None
        old_ws = sample.workshop_status
        if old_ws is not None:
            sample.workshop_status = None
            audit_old_values['workshop_status'] = (old_ws, None)
            extra_updated.append('Статус мастерской')

        # manufacturing_deadline → None
        old_md = sample.manufacturing_deadline
        if old_md is not None:
            sample.manufacturing_deadline = None
            audit_old_values['manufacturing_deadline'] = (old_md, None)
            extra_updated.append('Срок изготовления')

        # further_movement → ''
        old_fm = sample.further_movement
        if old_fm:
            sample.further_movement = ''
            audit_old_values['further_movement'] = (old_fm, '')
            extra_updated.append('Дальнейшее движение')

        # cutting_standard → None
        old_cs = sample.cutting_standard_id
        if old_cs is not None:
            sample.cutting_standard_id = None
            audit_old_values['cutting_standard'] = (old_cs, None)
            extra_updated.append('Стандарт на нарезку')

    return extra_updated


def _handle_moisture_toggle(request, sample, old_value, new_value, audit_old_values):
    """
    ⭐ v3.20.0: Обрабатывает включение/отключение влагонасыщения на уже существующем образце.

    Отключение (True → False):
      - moisture_sample_id = None

    Включение: ничего автоматического — moisture_sample_id задаётся через FK-поле формы.
    Статус образца НЕ меняется автоматически.
    """
    extra_updated = []

    if old_value and not new_value:
        # ─── Отключение влагонасыщения ───
        old_ms = sample.moisture_sample_id
        if old_ms is not None:
            sample.moisture_sample_id = None
            audit_old_values['moisture_sample'] = (old_ms, None)
            extra_updated.append('Образец влагонасыщения')

    return extra_updated


# ─────────────────────────────────────────────────────────────
# Парсинг и пересчёт
# ─────────────────────────────────────────────────────────────

def _parse_datetime_value(form_value):
    """Парсит datetime из формы (YYYY-MM-DDTHH:MM или YYYY-MM-DD)."""
    if 'T' in form_value:
        dt = datetime.strptime(form_value, '%Y-%m-%dT%H:%M')
    else:
        dt = datetime.strptime(form_value, '%Y-%m-%d').replace(hour=12, minute=0)
    return make_aware(dt)


def _recalculate_auto_fields(sample, changed_fields):
    """
    Пересчитывает автоматические поля образца,
    зависящие от изменённых полей.

    changed_fields: set кодов полей, которые были изменены.
    Вызывается ПЕРЕД sample.save().
    """
    fields_to_recalc = set()
    for field_code in changed_fields:
        deps = AUTO_FIELD_DEPENDENCIES.get(field_code, set())
        fields_to_recalc.update(deps)

    if not fields_to_recalc:
        return

    # test_code / test_type (из стандарта)
    if 'test_code' in fields_to_recalc or 'test_type' in fields_to_recalc:
        # ⭐ v3.13.0: берём test_code/test_type из первого стандарта
        if sample.pk:
            first_standard = sample.standards.order_by('samplestandard__id').first()
            if first_standard:
                sample.test_code = first_standard.test_code
                sample.test_type = first_standard.test_type

    # cipher пересчитывается автоматически в save() — ничего не нужно

    # pi_number
    if 'pi_number' in fields_to_recalc:
        # ⭐ v3.32.0: report_type — запятая-разделённый список
        report_types = set(sample.report_type.split(',')) if sample.report_type else set()
        if report_types - {'WITHOUT_REPORT'}:
            old_pi = sample.pi_number
            new_pi = sample.generate_pi_number()
            if old_pi and f"/{sample.sequence_number}-" in old_pi:
                sample.pi_number = new_pi

    # deadline
    if 'deadline' in fields_to_recalc:
        if sample.working_days and sample.sample_received_date:
            sample.deadline = sample.calculate_deadline()

    # manufacturing_deadline
    if 'manufacturing_deadline' in fields_to_recalc:
        if sample.manufacturing and sample.working_days and sample.sample_received_date:
            if sample.further_movement == 'TO_CLIENT_DEPT':
                sample.manufacturing_deadline = sample.deadline
            else:
                sample.manufacturing_deadline = sample.calculate_manufacturing_deadline()
        elif not sample.manufacturing:
            sample.manufacturing_deadline = None


def save_sample_fields(request, sample):
    """
    Сохраняет изменённые поля образца из POST-данных.
    M2M-поля обрабатываются отдельно через промежуточные таблицы.
    Возвращает список названий обновлённых полей.
    """
    updated_fields = []
    changed_field_codes = set()
    m2m_updates = []
    audit_old_values = {}  # ⭐ v3.14.0: {field_code: (old, new)} для аудит-лога

    all_columns = JournalColumn.objects.filter(
        journal__code='SAMPLES', is_active=True
    )

    for column in all_columns:
        field_code = column.code

        if not PermissionChecker.can_edit(request.user, 'SAMPLES', field_code):
            # Регистраторы могут менять status при активной разморозке
            if field_code == 'status' and request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD'):
                unfrozen_key = f'unfrozen_registration_{sample.id}'
                if not request.session.get(unfrozen_key, False):
                    continue
            else:
                continue

        if field_code in AUTO_FIELDS:
            continue

        # Серверная защита заморозки блоков
        is_frozen, _ = _is_field_frozen(field_code, request.user, sample, request=request)
        if is_frozen:
            continue

        try:
            field_obj = Sample._meta.get_field(field_code)
        except FieldDoesNotExist:
            continue

        # M2M-поля: собираем для обработки после save()
        if isinstance(field_obj, models.ManyToManyField):
            if field_code not in request.POST:
                continue
            selected_ids = request.POST.getlist(field_code)
            m2m_updates.append((field_code, column.name, selected_ids))
            continue

        # BooleanField: unchecked чекбокс не отправляется в POST
        if isinstance(field_obj, models.BooleanField):
            new_value = request.POST.get(field_code) == 'on'
            old_value = getattr(sample, field_code)
            if old_value != new_value:
                audit_old_values[field_code] = (old_value, new_value)  # ⭐ аудит
                setattr(sample, field_code, new_value)
                updated_fields.append(column.name)
                changed_field_codes.add(field_code)
            continue

        # ⭐ v3.32.0: report_type — множественный выбор (чекбоксы)
        if field_code == 'report_type':
            selected_types = request.POST.getlist('report_type')
            form_value = ','.join(selected_types) if selected_types else ''
        else:
            form_value = request.POST.get(field_code)
        if form_value is None:
            continue

        # Валидация «только латиница»
        needs_latin_check = False
        if field_code in LATIN_ONLY_FIELDS and form_value:
            needs_latin_check = True
        elif field_code in LATIN_ONLY_IF_MI and form_value:
            if sample.laboratory and sample.laboratory.code == 'MI':
                needs_latin_check = True

        if needs_latin_check:
            is_valid, error_msg = _validate_latin_only(field_code, form_value)
            if not is_valid:
                messages.error(request, f'Поле «{column.name}»: {error_msg}')
                continue

        old_value = getattr(sample, field_code)

        # DateTimeField (проверяем ДО DateField)
        if isinstance(field_obj, models.DateTimeField):
            if form_value:
                new_value = _parse_datetime_value(form_value)

                # ⭐ v3.16.0: Сравниваем с точностью до минут,
                # т.к. HTML input datetime-local обрезает секунды
                def _trunc_minutes(dt):
                    return dt.replace(second=0, microsecond=0) if dt else None

                if _trunc_minutes(old_value) != _trunc_minutes(new_value):
                    audit_old_values[field_code] = (old_value, new_value)  # ⭐ аудит
                    setattr(sample, field_code, new_value)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)
            elif old_value is not None:
                if field_obj.null:
                    audit_old_values[field_code] = (old_value, None)  # ⭐ аудит
                    setattr(sample, field_code, None)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)

        elif isinstance(field_obj, models.DateField):
            if form_value:
                new_value = datetime.strptime(form_value, '%Y-%m-%d').date()
                if old_value != new_value:
                    audit_old_values[field_code] = (old_value, new_value)  # ⭐ аудит
                    setattr(sample, field_code, new_value)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)
            elif old_value is not None:
                if field_obj.null:
                    audit_old_values[field_code] = (old_value, None)  # ⭐ аудит
                    setattr(sample, field_code, None)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)

        elif isinstance(field_obj, models.ForeignKey):
            old_id = getattr(sample, f'{field_code}_id')
            if form_value:
                new_id = int(form_value)
                if old_id != new_id:
                    audit_old_values[field_code] = (old_id, new_id)  # ⭐ аудит
                    setattr(sample, f'{field_code}_id', new_id)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)
            elif old_id is not None:
                if field_obj.null:
                    audit_old_values[field_code] = (old_id, None)  # ⭐ аудит
                    setattr(sample, f'{field_code}_id', None)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)

        elif isinstance(field_obj, models.IntegerField):
            if form_value:
                new_value = int(form_value)
                if old_value != new_value:
                    audit_old_values[field_code] = (old_value, new_value)  # ⭐ аудит
                    setattr(sample, field_code, new_value)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)
            else:
                if not field_obj.null:
                    default_val = field_obj.default if field_obj.has_default() else 0
                    if old_value != default_val:
                        audit_old_values[field_code] = (old_value, default_val)  # ⭐ аудит
                        setattr(sample, field_code, default_val)
                        updated_fields.append(column.name)
                        changed_field_codes.add(field_code)
                elif old_value is not None:
                    audit_old_values[field_code] = (old_value, None)  # ⭐ аудит
                    setattr(sample, field_code, None)
                    updated_fields.append(column.name)
                    changed_field_codes.add(field_code)

        else:
            # Текстовые поля (CharField, TextField)
            if field_obj.choices and not form_value:
                continue

            # Валидация статуса при разморозке регистраторами
            if field_code == 'status' and request.user.role in ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD'):
                allowed_statuses = {'CANCELLED', 'PENDING_VERIFICATION', sample.status}
                if form_value not in allowed_statuses:
                    messages.error(request, f'Недопустимый статус: {form_value}')
                    continue

            if old_value != form_value:
                audit_old_values[field_code] = (old_value, form_value)  # ⭐ аудит
                setattr(sample, field_code, form_value)
                updated_fields.append(column.name)
                changed_field_codes.add(field_code)

    # Пересчёт автополей при изменении зависимостей
    if changed_field_codes:
        _recalculate_auto_fields(sample, changed_field_codes)

    # ⭐ v3.20.0: Обработка включения/отключения нарезки и влагонасыщения
    if 'manufacturing' in changed_field_codes:
        old_mfg = not sample.manufacturing  # инвертируем, т.к. уже изменено
        extra = _handle_manufacturing_toggle(
            request, sample, old_mfg, sample.manufacturing, audit_old_values
        )
        updated_fields.extend(extra)

    if 'moisture_conditioning' in changed_field_codes:
        old_mc = not sample.moisture_conditioning  # инвертируем
        extra = _handle_moisture_toggle(
            request, sample, old_mc, sample.moisture_conditioning, audit_old_values
        )
        updated_fields.extend(extra)

    # Синхронизация: при отмене образца автоматически отменяем workshop_status
    if sample.manufacturing and sample.status == 'CANCELLED' and sample.workshop_status != 'CANCELLED':
        sample.workshop_status = WorkshopStatus.CANCELLED
        updated_fields.append('Статус в мастерской')

    sample.save()

    # ⭐ v3.14.0: Логируем изменения обычных полей
    if audit_old_values:
        log_field_changes(
            request, 'sample', sample.id, audit_old_values,
            action='sample_updated',
        )

    # Обрабатываем M2M-поля через промежуточные таблицы (после save)
    for field_code, column_name, selected_ids in m2m_updates:
        if handle_m2m_update(sample, field_code, selected_ids, request=request):
            updated_fields.append(column_name)

    return updated_fields

def handle_sample_save(request, sample):
    """Обрабатывает сохранение образца: сохраняет поля, показывает сообщение, делает redirect."""
    try:
        with transaction.atomic():
            updated_fields = save_sample_fields(request, sample)
            if updated_fields:
                messages.success(
                    request,
                    f'Образец успешно обновлён. Изменены поля: {", ".join(updated_fields)}'
                )
            else:
                messages.info(request, 'Изменений не обнаружено')
    except Exception as e:
        logger.exception('Ошибка при сохранении образца %s', sample.id)
        messages.error(request, f'Ошибка при сохранении: {e}')

    return redirect('sample_detail', sample_id=sample.id)


def handle_m2m_update(sample, field_code, selected_ids, request=None):
    """
    Обновляет M2M связи (СИ, ИО, операторы, стандарты).
    Возвращает True если были изменения.
    """
    m2m_config = {
        'standards': (SampleStandard, 'standard_id'),  # ⭐ v3.13.0
        'measuring_instruments': (SampleMeasuringInstrument, 'equipment_id'),
        'testing_equipment': (SampleTestingEquipment, 'equipment_id'),
        'operators': (SampleOperator, 'user_id'),
        'manufacturing_measuring_instruments': (SampleManufacturingMeasuringInstrument, 'equipment_id'),
        'manufacturing_testing_equipment': (SampleManufacturingTestingEquipment, 'equipment_id'),
        'manufacturing_operators': (SampleManufacturingOperator, 'user_id'),
        'manufacturing_auxiliary_equipment': (SampleManufacturingAuxiliaryEquipment, 'equipment_id'),
        'auxiliary_equipment': (SampleAuxiliaryEquipment, 'equipment_id'),
    }

    config = m2m_config.get(field_code)
    if not config:
        return False

    through_model, id_field = config

    current_ids = set(
        through_model.objects.filter(sample=sample)
        .values_list(id_field, flat=True)
    )
    new_ids = set(int(id) for id in selected_ids if id)

    if current_ids == new_ids:
        return False

    # ⭐ v3.14.0: Логируем M2M-изменения
    if request:
        log_m2m_changes(
            request=request,
            entity_type='sample',
            entity_id=sample.id,
            field_name=field_code,
            old_ids=current_ids,
            new_ids=new_ids,
        )

    through_model.objects.filter(sample=sample).delete()
    for obj_id in new_ids:
        through_model.objects.create(sample=sample, **{id_field: obj_id})

    # ⭐ v3.13.0: При изменении стандартов — пересчитать test_code/test_type
    if field_code == 'standards' and new_ids:
        from core.models import Standard
        first_standard = Standard.objects.filter(id__in=new_ids).order_by('id').first()
        if first_standard:
            sample.test_code = first_standard.test_code
            sample.test_type = first_standard.test_type
            sample.cipher = sample.generate_cipher()
            # Пересчёт pi_number если был автосгенерирован
            old_pi = sample.pi_number
            if old_pi and f"/{sample.sequence_number}-" in old_pi:
                sample.pi_number = sample.generate_pi_number()
            sample.save()

    return True

def _validate_trainee_for_draft(sample):
    """
    Проверяет, что среди назначенных испытателей есть хотя бы один
    не-стажёр. Вызывается при выпуске черновика протокола (draft_ready).

    Возвращает (is_valid: bool, error_message: str или None).
    """
    operator_ids = SampleOperator.objects.filter(
        sample=sample
    ).values_list('user_id', flat=True)

    if not operator_ids:
        return True, None

    operators = User.objects.filter(id__in=operator_ids, is_active=True)
    has_non_trainee = operators.filter(is_trainee=False).exists()

    if not has_non_trainee:
        return False, (
            'Невозможно выпустить черновик протокола: '
            'среди испытателей отсутствует аттестованный сотрудник. '
            'Добавьте наставника или другого аттестованного испытателя.'
        )

    return True, None