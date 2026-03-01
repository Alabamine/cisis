"""
CISIS v3.19.0 — Акты приёма-передачи: views

Файл: core/views/act_views.py

Функции:
- acts_registry       — реестр всех актов (отдельная страница)
- act_create          — создание акта
- act_detail          — просмотр/редактирование акта
- api_contract_acts   — AJAX: акты по договору (для каскада при регистрации)
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, F

from core.models import (
    AcceptanceAct, AcceptanceActLaboratory,
    Client, Contract, Laboratory,
)
from core.views.audit import log_action, log_field_changes
from core.views.file_views import get_files_for_entity
from core.permissions import PermissionChecker

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Проверки доступа
# ─────────────────────────────────────────────────────────────

def _check_acts_access(user):
    return PermissionChecker.can_view(user, 'CLIENTS', 'access')

def _can_edit_acts(user):
    return PermissionChecker.can_edit(user, 'CLIENTS', 'access')


# ─────────────────────────────────────────────────────────────
# Выпадающие списки (значения для шаблонов)
# ─────────────────────────────────────────────────────────────

ACT_CHOICES = {
    'document_status': [
        ('', '—'),
        ('SCANS_RECEIVED', 'Получены сканы'),
        ('ORIGINALS_RECEIVED', 'Получены оригиналы'),
    ],
    'payment_terms': [
        ('', '—'),
        ('PREPAID', 'Предоплата'),
        ('POSTPAID', 'Постоплата'),
        ('ADVANCE_50', 'Аванс 50%'),
        ('ADVANCE_30', 'Аванс 30%'),
        ('OTHER', 'Другое'),
    ],
    'document_flow': [
        ('', '—'),
        ('PAPER', 'Бумажный'),
        ('EDO', 'ЭДО'),
    ],
    'closing_status': [
        ('', '—'),
        ('PREPARED', 'Подготовлено'),
        ('SENT_TO_CLIENT', 'Передано заказчику'),
        ('RECEIVED', 'Получено'),
        ('CANCELLED', 'Отмена'),
    ],
    'work_status': [
        ('IN_PROGRESS', 'В работе'),
        ('CLOSED', 'Работы закрыты'),
        ('CANCELLED', 'Отмена'),
    ],
    'sending_method': [
        ('', '—'),
        ('COURIER', 'Курьер'),
        ('EMAIL', 'Отправлены по электронной почте'),
        ('RUSSIAN_POST', 'Отправлены Почтой России'),
        ('GARANTPOST', 'Отправлены Гарантпост'),
        ('IN_PERSON', 'Переданы нарочно'),
    ],
}

# Словари для отображения значений в реестре
ACT_DISPLAY = {}
for field, choices in ACT_CHOICES.items():
    ACT_DISPLAY[field] = dict(choices)


# ─────────────────────────────────────────────────────────────
# Реестр актов
# ─────────────────────────────────────────────────────────────

@login_required
def acts_registry(request):
    if not _check_acts_access(request.user):
        messages.error(request, 'У вас нет доступа к реестру актов')
        return redirect('workspace_home')

    # Фильтры
    search = request.GET.get('q', '').strip()
    client_id = request.GET.get('client', '')
    work_status = request.GET.get('work_status', '')
    lab_id = request.GET.get('laboratory', '')

    acts = AcceptanceAct.objects.select_related(
        'contract__client', 'created_by'
    ).prefetch_related('act_laboratories__laboratory').all()

    if search:
        acts = acts.filter(
            Q(document_name__icontains=search) |
            Q(doc_number__icontains=search) |
            Q(contract__client__name__icontains=search) |
            Q(contract__number__icontains=search)
        )

    if client_id:
        acts = acts.filter(contract__client_id=client_id)

    if work_status:
        acts = acts.filter(work_status=work_status)

    if lab_id:
        acts = acts.filter(act_laboratories__laboratory_id=lab_id)

    acts = acts.order_by('-created_at')

    # Данные для фильтров
    clients = Client.objects.filter(is_active=True).order_by('name')
    laboratories = Laboratory.objects.filter(
        is_active=True, department_type='LAB'
    ).order_by('name')

    # Добавляем прогресс и deadline_check к каждому акту
    acts_data = []
    for act in acts:
        labs = act.act_laboratories.select_related('laboratory').all()
        acts_data.append({
            'act': act,
            'progress': act.progress,
            'deadline_check': act.deadline_check,
            'laboratories': labs,
        })

    return render(request, 'core/acceptance_acts_registry.html', {
        'acts_data': acts_data,
        'total_count': len(acts_data),
        'search': search,
        'filter_client': client_id,
        'filter_work_status': work_status,
        'filter_lab': lab_id,
        'clients': clients,
        'laboratories': laboratories,
        'work_status_choices': ACT_CHOICES['work_status'],
        'display': ACT_DISPLAY,
        'can_edit': _can_edit_acts(request.user),
    })


# ─────────────────────────────────────────────────────────────
# Создание акта
# ─────────────────────────────────────────────────────────────

@login_required
def act_create(request):
    if not _can_edit_acts(request.user):
        messages.error(request, 'Нет прав на создание актов')
        return redirect('acts_registry')

    if request.method == 'POST':
        return _save_act(request, act=None)

    # GET — форма создания
    # Предзаполнение из query params (если пришли со страницы клиента)
    preset_contract_id = request.GET.get('contract_id', '')
    preset_client_id = request.GET.get('client_id', '')

    clients = Client.objects.filter(is_active=True).order_by('name')
    laboratories = Laboratory.objects.filter(
        is_active=True, department_type__in=['LAB', 'WORKSHOP']
    ).order_by('name')

    context = {
        'act': None,
        'clients': clients,
        'laboratories': laboratories,
        'choices': ACT_CHOICES,
        'can_edit': True,
        'preset_contract_id': preset_contract_id,
        'preset_client_id': preset_client_id,
    }
    return render(request, 'core/act_detail.html', context)


# ─────────────────────────────────────────────────────────────
# Просмотр / редактирование акта
# ─────────────────────────────────────────────────────────────

@login_required
def act_detail(request, act_id):
    if not _check_acts_access(request.user):
        messages.error(request, 'У вас нет доступа к актам')
        return redirect('workspace_home')

    act = get_object_or_404(
        AcceptanceAct.objects.select_related('contract__client', 'created_by'),
        id=act_id,
    )
    can_edit = _can_edit_acts(request.user)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'Нет прав на редактирование')
            return redirect('act_detail', act_id=act_id)
        return _save_act(request, act=act)

    # GET — форма просмотра/редактирования
    clients = Client.objects.filter(is_active=True).order_by('name')
    laboratories = Laboratory.objects.filter(
        is_active=True, department_type__in=['LAB', 'WORKSHOP']
    ).order_by('name')

    # Текущие лаборатории акта
    act_lab_ids = set(
        act.act_laboratories.values_list('laboratory_id', flat=True)
    )

    # Образцы по акту
    from core.models import Sample
    samples = Sample.objects.filter(
        acceptance_act_id=act_id
    ).select_related('laboratory').order_by('sequence_number')
    # Прогресс по лабораториям (для блока дат завершения)
    from core.models import Laboratory as Lab
    ALL_LAB_CODES = ['MI', 'ACT', 'TA', 'ChA', 'WORKSHOP']
    all_labs = Lab.objects.filter(code__in=ALL_LAB_CODES).order_by('code')

    labs_progress = []
    for lab in all_labs:
        lab_samples = samples.filter(laboratory_id=lab.id)
        total = lab_samples.count()

        if total == 0:
            labs_progress.append({
                'laboratory': lab,
                'total': 0,
                'completed': 0,
                'cancelled': 0,
                'completed_date': None,
            })
            continue

        completed = lab_samples.filter(
            status__in=['COMPLETED', 'PROTOCOL_ISSUED', 'REPLACEMENT_PROTOCOL']
        ).count()
        cancelled = lab_samples.filter(status='CANCELLED').count()

        # Автовычисление completed_date
        al = act.act_laboratories.filter(laboratory_id=lab.id).first()
        completed_date = None
        if al:
            if (completed + cancelled) == total and not al.completed_date:
                al.completed_date = al.compute_completed_date()
                if al.completed_date:
                    al.save()
            elif al.completed_date and (completed + cancelled) < total:
                al.completed_date = None
                al.save()
            completed_date = al.completed_date

        labs_progress.append({
            'laboratory': lab,
            'total': total,
            'completed': completed,
            'cancelled': cancelled,
            'completed_date': completed_date,
        })

    # Файлы акта и договора (v3.21.1)
    act_files = get_files_for_entity(request.user, 'acceptance_act', act.id)
    contract_files = get_files_for_entity(request.user, 'contract', act.contract_id)
    can_edit_files = PermissionChecker.can_edit(request.user, 'FILES', 'clients_files')

    context = {
        'act': act,
        'clients': clients,
        'laboratories': laboratories,
        'act_lab_ids': act_lab_ids,
        'choices': ACT_CHOICES,
        'can_edit': can_edit,
        'progress': act.progress,
        'deadline_check': act.deadline_check,
        'samples': samples,
        'labs_progress': labs_progress,
        'act_files': act_files,
        'contract_files': contract_files,
        'can_edit_files': can_edit_files,
    }
    return render(request, 'core/act_detail.html', context)


# ─────────────────────────────────────────────────────────────
# Сохранение акта (общая логика для create и edit)
# ─────────────────────────────────────────────────────────────

def _save_act(request, act=None):
    """Сохраняет акт. act=None → создание, act=object → редактирование."""
    is_new = act is None

    # --- Парсинг данных формы ---
    contract_id = request.POST.get('contract_id', '').strip()
    if not contract_id:
        messages.error(request, 'Договор обязателен')
        return redirect('acts_registry')

    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        messages.error(request, 'Договор не найден')
        return redirect('acts_registry')

    # Текстовые / select поля
    fields_map = {
        'doc_number': ('doc_number', ''),
        'document_name': ('document_name', ''),
        'document_status': ('document_status', ''),
        'payment_terms': ('payment_terms', ''),
        'comment': ('comment', ''),
        'payment_invoice': ('payment_invoice', ''),
        'completion_act': ('completion_act', ''),
        'invoice_number': ('invoice_number', ''),
        'document_flow': ('document_flow', ''),
        'closing_status': ('closing_status', ''),
        'work_status': ('work_status', 'IN_PROGRESS'),
        'sending_method': ('sending_method', ''),
    }

    data = {}
    for form_name, (field_name, default) in fields_map.items():
        data[field_name] = request.POST.get(form_name, default).strip()

    # Даты
    date_fields = ['samples_received_date', 'work_deadline', 'advance_date', 'full_payment_date']
    for df in date_fields:
        val = request.POST.get(df, '').strip()
        data[df] = datetime.strptime(val, '%Y-%m-%d').date() if val else None

    # Числовые
    services_count_str = request.POST.get('services_count', '').strip()
    data['services_count'] = int(services_count_str) if services_count_str else None

    work_cost_str = request.POST.get('work_cost', '').strip()
    try:
        data['work_cost'] = Decimal(work_cost_str) if work_cost_str else None
    except InvalidOperation:
        data['work_cost'] = None

    # Булев
    data['has_subcontract'] = request.POST.get('has_subcontract') == 'on'

    # Лаборатории (чекбоксы)
    lab_ids = request.POST.getlist('laboratories')
    lab_ids = [int(x) for x in lab_ids if x.isdigit()]

    # --- Сохранение ---
    try:
        if is_new:
            act = AcceptanceAct()
            act.created_by = request.user

        old_values = {}
        if not is_new:
            for key in data:
                old_values[key] = getattr(act, key, None)

        act.contract = contract
        for key, val in data.items():
            setattr(act, key, val)
        act.save()

        # M2M лаборатории
        existing_lab_ids = set(
            AcceptanceActLaboratory.objects.filter(act=act).values_list('laboratory_id', flat=True)
        )
        new_lab_ids = set(lab_ids)

        # Добавить новые
        for lid in new_lab_ids - existing_lab_ids:
            AcceptanceActLaboratory.objects.create(act=act, laboratory_id=lid)

        # Удалить убранные
        AcceptanceActLaboratory.objects.filter(
            act=act, laboratory_id__in=existing_lab_ids - new_lab_ids
        ).delete()

        # Аудит
        if is_new:
            log_action(request, 'acceptance_act', act.id, 'create',
                       extra_data={'document_name': act.document_name, 'contract_id': contract.id})
            messages.success(request, f'Акт «{act.document_name or act.doc_number}» создан')
        else:
            changes = {}
            for key in data:
                old_val = old_values.get(key)
                new_val = getattr(act, key)
                if str(old_val or '') != str(new_val or ''):
                    changes[key] = (old_val, new_val)
            if changes:
                log_field_changes(request, 'acceptance_act', act.id, changes)
            messages.success(request, f'Акт «{act.document_name or act.doc_number}» обновлён')

        return redirect('act_detail', act_id=act.id)

    except Exception as e:
        logger.exception('Ошибка сохранения акта')
        messages.error(request, f'Ошибка: {e}')
        return redirect('acts_registry')


# ─────────────────────────────────────────────────────────────
# AJAX: акты по договору (для каскада при регистрации образца)
# ─────────────────────────────────────────────────────────────

@login_required
def api_contract_acts(request, contract_id):
    """Возвращает JSON список актов для данного договора."""
    acts = AcceptanceAct.objects.filter(
        contract_id=contract_id
    ).order_by('-created_at')

    result = []
    for act in acts:
        labs = list(
            act.act_laboratories.values_list('laboratory__code_display', flat=True)
        )
        result.append({
            'id': act.id,
            'doc_number': act.doc_number,
            'document_name': act.document_name,
            'work_deadline': str(act.work_deadline) if act.work_deadline else None,
            'laboratories': labs,
            'work_status': act.work_status,
            'progress': act.progress,
        })

    return JsonResponse(result, safe=False)