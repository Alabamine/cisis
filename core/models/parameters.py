"""
CISIS v3.22.0 — Модели показателей (определяемых параметров).

Три уровня:
  Parameter         — единый справочник показателей (без дублей)
  StandardParameter — привязка показателя к стандарту + настройки
  SampleParameter   — показатели конкретного образца (выбранные + кастомные)
"""

from django.db import models


class ParameterCategory(models.TextChoices):
    MECHANICAL = 'MECHANICAL', 'Механические'
    THERMAL = 'THERMAL', 'Термические'
    CHEMICAL = 'CHEMICAL', 'Химические'
    DIMENSIONAL = 'DIMENSIONAL', 'Размерные'
    OTHER = 'OTHER', 'Прочие'


class ParameterRole(models.TextChoices):
    PRIMARY = 'PRIMARY', 'Основной'
    AUXILIARY = 'AUXILIARY', 'Вспомогательный'
    CALCULATED = 'CALCULATED', 'Расчётный'


class ResultStatus(models.TextChoices):
    PENDING = 'PENDING', 'Ожидает'
    FILLED = 'FILLED', 'Заполнен'
    VALIDATED = 'VALIDATED', 'Подтверждён'


class Parameter(models.Model):
    """Единый справочник показателей (без привязки к стандарту)."""

    name = models.CharField('Название', max_length=255)
    name_en = models.CharField('Название (EN)', max_length=255, blank=True, null=True)
    unit = models.CharField('Единица измерения', max_length=50, blank=True, null=True)
    description = models.TextField('Описание', blank=True, null=True)
    category = models.CharField(
        'Категория',
        max_length=50,
        choices=ParameterCategory.choices,
        default=ParameterCategory.OTHER,
    )
    is_active = models.BooleanField('Активен', default=True)
    display_order = models.IntegerField('Порядок отображения', default=0)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        managed = False
        db_table = 'parameters'
        ordering = ['display_order', 'name']
        verbose_name = 'Показатель'
        verbose_name_plural = 'Показатели'
        constraints = [
            models.UniqueConstraint(fields=['name', 'unit'], name='uq_parameters_name_unit'),
        ]

    def __str__(self):
        if self.unit:
            return f'{self.name} ({self.unit})'
        return self.name

    @property
    def display_name(self):
        """Название с единицей для UI."""
        if self.unit:
            return f'{self.name}, {self.unit}'
        return self.name


class StandardParameter(models.Model):
    """Привязка показателя к стандарту с настройками роли, порядка и условий."""

    standard = models.ForeignKey(
        'Standard',
        on_delete=models.CASCADE,
        related_name='standard_parameters',
        verbose_name='Стандарт',
    )
    parameter = models.ForeignKey(
        Parameter,
        on_delete=models.CASCADE,
        related_name='standard_links',
        verbose_name='Показатель',
    )
    parameter_role = models.CharField(
        'Роль',
        max_length=20,
        choices=ParameterRole.choices,
        default=ParameterRole.PRIMARY,
    )
    is_default = models.BooleanField('По умолчанию', default=True)
    unit_override = models.CharField(
        'Ед. изм. (переопределение)', max_length=50, blank=True, null=True
    )
    test_conditions = models.CharField(
        'Условия испытания', max_length=500, blank=True, null=True
    )
    precision = models.IntegerField('Точность (знаков)', blank=True, null=True)
    report_group = models.CharField(
        'Группа в протоколе', max_length=100, blank=True, null=True
    )
    report_order = models.IntegerField('Порядок в протоколе', default=0)
    display_order = models.IntegerField('Порядок в UI', default=0)
    formula = models.TextField('Формула расчёта', blank=True, null=True)
    depends_on = models.JSONField('Зависит от (parameter_id[])', blank=True, null=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        managed = False
        db_table = 'standard_parameters'
        ordering = ['display_order', 'parameter__name']
        verbose_name = 'Показатель стандарта'
        verbose_name_plural = 'Показатели стандартов'
        constraints = [
            models.UniqueConstraint(
                fields=['standard', 'parameter'], name='uq_standard_parameter'
            ),
        ]

    def __str__(self):
        role_label = self.get_parameter_role_display()
        return f'{self.parameter} [{role_label}] — {self.standard}'

    @property
    def effective_unit(self):
        """Единица измерения: переопределённая или из справочника."""
        return self.unit_override or self.parameter.unit or ''

    @property
    def display_name(self):
        """Полное название для UI."""
        unit = self.effective_unit
        name = self.parameter.name
        if unit:
            return f'{name}, {unit}'
        return name


class SampleParameter(models.Model):
    """Показатель конкретного образца — выбранный из стандарта или кастомный."""

    sample = models.ForeignKey(
        'Sample',
        on_delete=models.CASCADE,
        related_name='sample_parameters',
        verbose_name='Образец',
    )
    standard_parameter = models.ForeignKey(
        StandardParameter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sample_links',
        verbose_name='Показатель стандарта',
    )
    custom_name = models.CharField('Кастомное название', max_length=255, blank=True, null=True)
    custom_unit = models.CharField('Кастомная ед. изм.', max_length=50, blank=True, null=True)
    is_selected = models.BooleanField(
        'Показывать в определяемых параметрах', default=True
    )
    display_order = models.IntegerField('Порядок отображения', default=0)

    # --- Задел на результаты (не используется в v3.22.0) ---
    result_numeric = models.DecimalField(
        'Числовой результат', max_digits=15, decimal_places=6, blank=True, null=True
    )
    result_text = models.CharField(
        'Текстовый результат', max_length=500, blank=True, null=True
    )
    result_status = models.CharField(
        'Статус результата',
        max_length=20,
        choices=ResultStatus.choices,
        blank=True,
        null=True,
    )
    tested_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tested_parameters',
        verbose_name='Испытатель',
    )
    tested_at = models.DateTimeField('Дата испытания', blank=True, null=True)
    notes = models.TextField('Примечания', blank=True, null=True)

    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'sample_parameters'
        ordering = ['display_order', 'id']
        verbose_name = 'Показатель образца'
        verbose_name_plural = 'Показатели образцов'
        constraints = [
            models.UniqueConstraint(
                fields=['sample', 'standard_parameter'],
                name='uq_sample_std_parameter',
            ),
        ]

    def __str__(self):
        return f'{self.effective_name} — образец #{self.sample_id}'

    @property
    def is_custom(self):
        return self.standard_parameter_id is None

    @property
    def effective_name(self):
        """Название: из стандарта или кастомное."""
        if self.is_custom:
            return self.custom_name or '(без названия)'
        return self.standard_parameter.parameter.name

    @property
    def effective_unit(self):
        """Единица измерения."""
        if self.is_custom:
            return self.custom_unit or ''
        return self.standard_parameter.effective_unit

    @property
    def effective_role(self):
        """Роль показателя (для кастомных — PRIMARY)."""
        if self.is_custom:
            return ParameterRole.PRIMARY
        return self.standard_parameter.parameter_role

    @property
    def display_name(self):
        """Полное название для UI."""
        unit = self.effective_unit
        name = self.effective_name
        if unit:
            return f'{name}, {unit}'
        return name
