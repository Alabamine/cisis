"""
Views для генерации этикеток образцов.
Генерирует PDF A4 с 8 этикетками на листе.
Разные шаблоны для разных лабораторий.
"""

import io
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from core.models import Sample, Laboratory
from core.permissions import PermissionChecker

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Регистрация шрифтов
# ─────────────────────────────────────────────────────────────
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS_DIR = os.path.join(BASE_DIR, 'fonts')

FONT_PATH = os.path.join(FONTS_DIR, 'DejaVuSans.ttf')
FONT_BOLD_PATH = os.path.join(FONTS_DIR, 'DejaVuSans-Bold.ttf')

try:
    pdfmetrics.registerFont(TTFont('DejaVu', FONT_PATH))
    pdfmetrics.registerFont(TTFont('DejaVuBold', FONT_BOLD_PATH))
    logger.info('Шрифты DejaVu успешно зарегистрированы')
except Exception as e:
    logger.exception(f'Не удалось загрузить шрифты DejaVu: {e}')

# ─────────────────────────────────────────────────────────────
# Константы макета
# ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4

COLS = 2
ROWS = 4
MARGIN_X = 10 * mm
MARGIN_Y = 8 * mm
GAP_X = 6 * mm
GAP_Y = 5 * mm

LABEL_W = (PAGE_W - 2 * MARGIN_X - (COLS - 1) * GAP_X) / COLS
LABEL_H = (PAGE_H - 2 * MARGIN_Y - (ROWS - 1) * GAP_Y) / ROWS

PADDING = 2 * mm
FONT_SIZE_TITLE = 7
FONT_SIZE_DATA = 5.5
FONT_SIZE_SMALL = 5
LINE_HEIGHT = FONT_SIZE_DATA * 0.45 * mm + 1.2 * mm


# ─────────────────────────────────────────────────────────────
# Шаблоны полей для каждой лаборатории
# ─────────────────────────────────────────────────────────────

# Каждый элемент: (label, field_code_или_None, is_bold_value)
# field_code=None означает пустую ячейку для ручного заполнения

LABEL_TEMPLATES = {
    # Универсальный шаблон для всех лабораторий (МИ, ХА, ТА, УКИ)
    'DEFAULT': {
        'name': 'Этикетка образца',
        'auto_fields': [
            ('Материал', 'material', False),
            ('Панель', 'panel_id', False),
            ('ID образца', 'cipher', False),
            ('Тип испыт.', 'test_type', False),
            ('Параметры', 'determined_parameters', False),
            ('Стандарт', 'standard_code', False),
            ('Отчётность', 'report_type', False),
            ('Пробоподг.', 'preparation', False),
            ('Примечания', 'notes', False),
            ('Кол-во обр.', 'sample_count_display', False),  # ⭐ v3.9.0: "6+1"
            ('Условия', 'test_conditions', True),
        ],
        'empty_fields': [
            ('Изготовил', ['ФИО', 'Дата']),
            ('Кондиц.(ИО)', ['Дата']),
            ('Фото', ['ДО №', 'ПОСЛЕ №']),
            ('Испытал', ['ФИО', 'Дата']),
            ('Оборудование', None),
        ],
    },
    # ⭐ v3.7.0 / v3.9.0: Этикетка мастерской
    'WORKSHOP': {
        'name': 'Мастерская',
        'auto_fields': [
            ('Срок изгот.', 'manufacturing_deadline', False),
            ('Материал', 'material', False),
            ('ID панели', 'panel_id', False),
            ('ID образца', 'cipher', False),
            ('Стандарт нарезки', 'cutting_standard_code', False),
            ('УЗК', 'uzk_required', False),
            ('Кол-во обр.', 'sample_count_display', False),  # ⭐ v3.9.0: "6+1"
            ('Передать', 'further_movement', False),
            ('Примечания', 'workshop_notes', False),  # ⭐ v3.9.0: workshop_notes вместо notes
        ],
        'empty_fields': [
            ('Изготовил', ['ФИО', 'Дата']),
        ],
    },
}


def _get_sample_value(sample, field_code):
    """Получает отображаемое значение поля образца."""
    if field_code == 'standard':
        return str(sample.standards) if sample.standards else '—'
    elif field_code == 'cutting_standard_code':
        if sample.cutting_standard:
            return sample.cutting_standard.code
            # Если не указан — показать основные стандарты
        std_codes = [s.code for s in sample.standards.all()]
        return ', '.join(std_codes) if std_codes else '—'
    elif field_code == 'standard_code':
        std_codes = [s.code for s in sample.standards.all()]
        return ', '.join(std_codes) if std_codes else '—'
    elif field_code == 'report_type':
        return sample.get_report_type_display() if sample.report_type else '—'
    # ⭐ v3.9.0: Количество образцов в формате "6+1"
    elif field_code == 'sample_count_display':
        return sample.sample_count_display
    elif field_code == 'sample_count':
        return f'{sample.sample_count} шт' if sample.sample_count else '—'
    elif field_code == 'uzk_required':
        return 'Да' if sample.uzk_required else 'Нет'
    elif field_code == 'further_movement':
        return sample.get_further_movement_display() if sample.further_movement else '—'
    elif field_code == 'deadline':
        return sample.deadline.strftime('%d.%m.%Y') if sample.deadline else '—'
    elif field_code == 'manufacturing_deadline':
        return sample.manufacturing_deadline.strftime('%d.%m.%Y') if sample.manufacturing_deadline else '—'
    elif field_code == 'cutting_standard_code':
        if sample.cutting_standard:
            return sample.cutting_standard.code
                # Если не указан — показать основные стандарты
        std_codes = [s.code for s in sample.standards.all()]
        return ', '.join(std_codes) if std_codes else '—'
    else:
        value = getattr(sample, field_code, None)
        return str(value) if value else '—'


# ─────────────────────────────────────────────────────────────
# Отрисовка одной этикетки
# ─────────────────────────────────────────────────────────────

def _draw_label(c, x, y, w, h, sample, template):
    """Рисует одну этикетку для образца по шаблону лаборатории."""

    inner_x = x + PADDING
    inner_w = w - 2 * PADDING
    cur_y = y + h - PADDING

    # Рамка
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h)

    def _truncate_text(text, font, font_size, max_width):
        """Обрезает текст если не помещается."""
        if c.stringWidth(text, font, font_size) <= max_width:
            return text
        while c.stringWidth(text + '…', font, font_size) > max_width and len(text) > 1:
            text = text[:-1]
        return text + '…'

    def draw_header(text):
        nonlocal cur_y
        cur_y -= FONT_SIZE_TITLE * 0.4 * mm + 1.2 * mm
        c.setFont('DejaVuBold', FONT_SIZE_TITLE)
        text = _truncate_text(text, 'DejaVuBold', FONT_SIZE_TITLE, inner_w)
        c.drawCentredString(x + w / 2, cur_y, text)
        cur_y -= 0.8 * mm
        c.setLineWidth(0.3)
        c.line(inner_x, cur_y, inner_x + inner_w, cur_y)
        cur_y -= 0.3 * mm

    def draw_data_row(label, value, bold_value=False):
        nonlocal cur_y
        cur_y -= LINE_HEIGHT

        c.setFont('DejaVuBold', FONT_SIZE_SMALL)
        c.drawString(inner_x, cur_y, label + ':')

        label_w = c.stringWidth(label + ': ', 'DejaVuBold', FONT_SIZE_SMALL)
        font = 'DejaVuBold' if bold_value else 'DejaVu'
        c.setFont(font, FONT_SIZE_DATA)

        max_val_w = inner_w - label_w - 1 * mm
        text = _truncate_text(str(value), font, FONT_SIZE_DATA, max_val_w)
        c.drawString(inner_x + label_w, cur_y, text)

    def draw_separator():
        nonlocal cur_y
        cur_y -= 0.8 * mm
        c.setLineWidth(0.2)
        c.setStrokeColorRGB(0.5, 0.5, 0.5)
        c.line(inner_x, cur_y, inner_x + inner_w, cur_y)
        c.setStrokeColorRGB(0, 0, 0)
        cur_y -= 0.3 * mm

    def draw_empty_row(label, cells=None):
        nonlocal cur_y
        cur_y -= LINE_HEIGHT

        c.setFont('DejaVu', FONT_SIZE_SMALL)
        c.drawString(inner_x, cur_y, label + ':')

        if cells:
            label_w = c.stringWidth(label + ': ', 'DejaVu', FONT_SIZE_SMALL)
            remaining_w = inner_w - label_w
            cell_w = remaining_w / len(cells)
            for i, cell_label in enumerate(cells):
                cx = inner_x + label_w + i * cell_w
                c.setFont('DejaVu', FONT_SIZE_SMALL - 0.5)
                c.drawString(cx, cur_y, cell_label + ' ___')
        else:
            label_w = c.stringWidth(label + ': ', 'DejaVu', FONT_SIZE_SMALL)
            c.setLineWidth(0.2)
            c.line(inner_x + label_w, cur_y - 0.3 * mm,
                   inner_x + inner_w, cur_y - 0.3 * mm)

    # ─── Содержимое этикетки ───

    # Автозаполняемые поля
    for label, field_code, bold in template['auto_fields']:
        value = _get_sample_value(sample, field_code)
        draw_data_row(label, value, bold_value=bold)

    # Разделитель
    draw_separator()

    # Пустые ячейки
    for label, cells in template['empty_fields']:
        draw_empty_row(label, cells)


# ─────────────────────────────────────────────────────────────
# Генерация PDF
# ─────────────────────────────────────────────────────────────

def _generate_labels_pdf(samples, lab_code):
    """
    Генерирует PDF с этикетками. Возвращает bytes.
    Для образцов с manufacturing=True автоматически добавляется
    этикетка мастерской перед лабораторной этикеткой.
    """
    template = LABEL_TEMPLATES.get(lab_code, LABEL_TEMPLATES['DEFAULT'])
    workshop_template = LABEL_TEMPLATES['WORKSHOP']

    # Собираем список этикеток: (sample, template_to_use)
    label_list = []
    for sample in samples:
        if sample.manufacturing:
            label_list.append((sample, workshop_template))
        label_list.append((sample, template))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f'Этикетки {template["name"]}')

    for label_idx, (sample, tpl) in enumerate(label_list):
        col = label_idx % COLS
        row = (label_idx // COLS) % ROWS

        # Новая страница
        if label_idx > 0 and label_idx % (COLS * ROWS) == 0:
            c.showPage()

        lx = MARGIN_X + col * (LABEL_W + GAP_X)
        ly = PAGE_H - MARGIN_Y - (row + 1) * LABEL_H - row * GAP_Y

        _draw_label(c, lx, ly, LABEL_W, LABEL_H, sample, tpl)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────

@login_required
def labels_page(request):
    """Страница генератора этикеток — выбор образцов и печать."""

    if not PermissionChecker.can_view(request.user, 'LABELS', 'access'):
        messages.error(request, 'У вас нет доступа к генератору этикеток')
        return redirect('workspace_home')

    laboratories = Laboratory.objects.all().order_by('code')

    lab_filter = request.GET.get('lab', '')

    samples = Sample.objects.select_related(
        'laboratory', 'client', 'cutting_standard'
    ).prefetch_related('standards').exclude(
        status='CANCELLED'
    ).order_by('-sequence_number')

    if lab_filter:
        samples = samples.filter(laboratory__code=lab_filter)

    samples = samples[:200]

    preselected_ids = request.GET.getlist('ids')

    return render(request, 'core/labels_page.html', {
        'samples': samples,
        'laboratories': laboratories,
        'lab_filter': lab_filter,
        'preselected_ids': preselected_ids,
    })


@login_required
def labels_generate(request):
    """Генерирует PDF с этикетками для выбранных образцов."""

    if request.method != 'POST':
        return redirect('labels_page')

    if not PermissionChecker.can_view(request.user, 'LABELS', 'access'):
        messages.error(request, 'У вас нет доступа к генератору этикеток')
        return redirect('workspace_home')

    sample_ids = request.POST.getlist('sample_ids')

    if not sample_ids:
        messages.error(request, 'Не выбрано ни одного образца')
        return redirect('labels_page')

    samples = Sample.objects.select_related(
        'laboratory', 'client', 'cutting_standard'
    ).prefetch_related('standards').filter(
        id__in=sample_ids
    ).order_by('sequence_number')

    if not samples.exists():
        messages.error(request, 'Образцы не найдены')
        return redirect('labels_page')

    try:
        pdf_bytes = _generate_labels_pdf(samples, 'DEFAULT')
    except Exception as e:
        logger.exception('Ошибка генерации этикеток')
        messages.error(request, f'Ошибка генерации PDF: {e}')
        return redirect('labels_page')

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="labels.pdf"'
    return response