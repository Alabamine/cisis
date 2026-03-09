"""
Модели файловой системы CISIS v3.21.0

Единая таблица files для всех файлов системы.
Полиморфная привязка к сущностям (образец, акт, договор, оборудование, стандарт).
Версионность, управление видимостью, превью.
"""

import os
import re
from django.db import models
from django.conf import settings


# =============================================================================
# КОНСТАНТЫ
# =============================================================================

class FileCategory:
    SAMPLE = 'SAMPLE'
    CLIENT = 'CLIENT'
    EQUIPMENT = 'EQUIPMENT'
    STANDARD = 'STANDARD'
    QMS = 'QMS'
    PERSONAL = 'PERSONAL'
    INBOX = 'INBOX'

    CHOICES = [
        (SAMPLE, 'Файлы образцов'),
        (CLIENT, 'Файлы клиентов'),
        (EQUIPMENT, 'Файлы оборудования'),
        (STANDARD, 'Стандарты'),
        (QMS, 'Файлы СМК'),
        (PERSONAL, 'Личные папки'),
        (INBOX, 'Входящие'),
    ]


class FileType:
    # SAMPLE
    PHOTO = 'PHOTO'
    RAW_DATA = 'RAW_DATA'
    DRAFT_PROTOCOL = 'DRAFT_PROTOCOL'
    PROTOCOL = 'PROTOCOL'
    # CLIENT
    CONTRACT_SCAN = 'CONTRACT_SCAN'
    CONTRACT_OTHER = 'CONTRACT_OTHER'
    ACT_SCAN = 'ACT_SCAN'
    ACT_FINANCE = 'ACT_FINANCE'
    ACT_OTHER = 'ACT_OTHER'
    # EQUIPMENT
    MANUAL = 'MANUAL'
    CERTIFICATE = 'CERTIFICATE'
    PASSPORT = 'PASSPORT'
    VERIFICATION_CERT = 'VERIFICATION_CERT'
    ATTESTATION_CERT = 'ATTESTATION_CERT'
    REPAIR_ACT = 'REPAIR_ACT'
    # STANDARD
    PDF = 'PDF'
    LINK = 'LINK'
    # QMS
    INSTRUCTION = 'INSTRUCTION'
    POLICY = 'POLICY'
    TEMPLATE = 'TEMPLATE'
    # PERSONAL / INBOX
    USER_FILE = 'USER_FILE'
    UNSORTED = 'UNSORTED'
    OTHER = 'OTHER'

    # Типы файлов, сгруппированные по категории (для выпадающих списков в UI)
    CHOICES_BY_CATEGORY = {
        FileCategory.SAMPLE: [
            (PHOTO, 'Фото образца'),
            (RAW_DATA, 'Выходные данные'),
            (DRAFT_PROTOCOL, 'Черновик протокола'),
            (PROTOCOL, 'Чистовик протокола'),
            (OTHER, 'Прочее'),
        ],
        FileCategory.CLIENT: [
            (CONTRACT_SCAN, 'Скан договора'),
            (CONTRACT_OTHER, 'Прочее по договору'),
            (ACT_SCAN, 'Скан акта'),
            (ACT_FINANCE, 'Финансовый документ'),
            (ACT_OTHER, 'Прочее по акту'),
        ],
        FileCategory.EQUIPMENT: [
            (VERIFICATION_CERT, 'Свидетельство о поверке'),
            (ATTESTATION_CERT, 'Акт аттестации'),
            (REPAIR_ACT, 'Акт ремонта'),
            (MANUAL, 'Инструкция'),
            (PASSPORT, 'Паспорт'),
            (OTHER, 'Прочее'),
        ],
        FileCategory.STANDARD: [
            (PDF, 'PDF стандарта'),
            (LINK, 'Ссылка на Техэксперт'),
        ],
        FileCategory.QMS: [
            (INSTRUCTION, 'Инструкция'),
            (POLICY, 'Политика'),
            (TEMPLATE, 'Шаблон'),
        ],
        FileCategory.PERSONAL: [
            (USER_FILE, 'Личный файл'),
        ],
        FileCategory.INBOX: [
            (UNSORTED, 'Неразобранное'),
        ],
    }


class FileVisibility:
    ALL = 'ALL'
    RESTRICTED = 'RESTRICTED'
    PRIVATE = 'PRIVATE'

    CHOICES = [
        (ALL, 'Все'),
        (RESTRICTED, 'Ограниченный'),
        (PRIVATE, 'Приватный'),
    ]


# =============================================================================
# ОСНОВНАЯ МОДЕЛЬ
# =============================================================================

class File(models.Model):
    """
    Единая модель для всех файлов системы.
    Заменяет старую SampleFile.
    """

    # --- Физическое расположение ---
    file_path = models.CharField(
        max_length=1000,
        verbose_name='Путь к файлу (от MEDIA_ROOT)'
    )
    original_name = models.CharField(
        max_length=500,
        verbose_name='Исходное имя файла'
    )
    file_size = models.BigIntegerField(
        verbose_name='Размер (байты)'
    )
    mime_type = models.CharField(
        max_length=100,
        default='',
        blank=True,
        verbose_name='MIME-тип'
    )

    # --- Категория и тип ---
    category = models.CharField(
        max_length=50,
        choices=FileCategory.CHOICES,
        verbose_name='Категория'
    )
    file_type = models.CharField(
        max_length=50,
        default='',
        blank=True,
        verbose_name='Тип файла'
    )

    # --- Полиморфная привязка ---
    sample = models.ForeignKey(
        'Sample', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='files',
        verbose_name='Образец'
    )
    acceptance_act = models.ForeignKey(
        'AcceptanceAct', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='files',
        verbose_name='Акт'
    )
    contract = models.ForeignKey(
        'Contract', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='files',
        verbose_name='Договор'
    )
    equipment = models.ForeignKey(
        'Equipment', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='files',
        db_column='equipment_id',
        verbose_name='Оборудование'
    )
    standard = models.ForeignKey(
        'Standard', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='files',
        verbose_name='Стандарт'
    )

    # --- Личная папка ---
    owner = models.ForeignKey(
        'User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='owned_files',
        db_column='owner_id',
        verbose_name='Владелец папки'
    )

    # --- Видимость ---
    visibility = models.CharField(
        max_length=20,
        choices=FileVisibility.CHOICES,
        default=FileVisibility.ALL,
        verbose_name='Видимость'
    )

    # --- Версионность ---
    version = models.IntegerField(
        default=1,
        verbose_name='Версия'
    )
    current_version = models.BooleanField(
        default=True,
        verbose_name='Актуальная версия'
    )
    replaces = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='replaced_by',
        db_column='replaces_id',
        verbose_name='Заменяет файл'
    )

    # --- Превью ---
    thumbnail_path = models.CharField(
        max_length=1000,
        null=True, blank=True,
        verbose_name='Путь к миниатюре'
    )

    # --- Метаданные ---
    description = models.CharField(
        max_length=1000,
        default='',
        blank=True,
        verbose_name='Описание'
    )
    uploaded_by = models.ForeignKey(
        'User', on_delete=models.RESTRICT,
        related_name='uploaded_files',
        db_column='uploaded_by_id',
        verbose_name='Загрузил'
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата загрузки'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалён'
    )
    deleted_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Дата удаления'
    )
    deleted_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='deleted_files',
        db_column='deleted_by_id',
        verbose_name='Удалил'
    )

    class Meta:
        db_table = 'files'
        managed = False
        ordering = ['-uploaded_at']
        verbose_name = 'Файл'
        verbose_name_plural = 'Файлы'

    def __str__(self):
        return f'{self.original_name} (v{self.version})'

    # ═══════════════════════════════════════════════════════════════
    # СВОЙСТВА
    # ═══════════════════════════════════════════════════════════════

    @property
    def full_path(self):
        """Абсолютный путь к файлу на диске"""
        return os.path.join(settings.MEDIA_ROOT, self.file_path)

    @property
    def full_thumbnail_path(self):
        """Абсолютный путь к миниатюре"""
        if self.thumbnail_path:
            return os.path.join(settings.MEDIA_ROOT, self.thumbnail_path)
        return None

    @property
    def extension(self):
        """Расширение файла"""
        return os.path.splitext(self.original_name)[1].lower()

    @property
    def is_image(self):
        """Является ли файл изображением"""
        return self.extension in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

    @property
    def is_pdf(self):
        """Является ли файл PDF"""
        return self.extension == '.pdf'

    @property
    def size_display(self):
        """Размер в читаемом формате"""
        size = self.file_size
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size < 1024.0:
                return f'{size:.1f} {unit}'
            size /= 1024.0
        return f'{size:.1f} ТБ'

    @property
    def entity(self):
        """Привязанная сущность (первая непустая)"""
        if self.sample_id:
            return self.sample
        if self.acceptance_act_id:
            return self.acceptance_act
        if self.contract_id:
            return self.contract
        if self.equipment_id:
            return self.equipment
        if self.standard_id:
            return self.standard
        return None

    @property
    def entity_type(self):
        """Тип привязанной сущности"""
        if self.sample_id:
            return 'sample'
        if self.acceptance_act_id:
            return 'acceptance_act'
        if self.contract_id:
            return 'contract'
        if self.equipment_id:
            return 'equipment'
        if self.standard_id:
            return 'standard'
        return None

    @property
    def version_history(self):
        """Все версии этого файла (включая текущую), от новой к старой"""
        # Найти корневой файл (самый первый в цепочке)
        root = self
        visited = {self.id}
        while root.replaces_id and root.replaces_id not in visited:
            visited.add(root.replaces_id)
            try:
                root = File.objects.get(id=root.replaces_id)
            except File.DoesNotExist:
                break

        # Собрать все версии от корня
        versions = [root]
        current = root
        while True:
            next_version = File.objects.filter(
                replaces_id=current.id
            ).first()
            if not next_version:
                break
            versions.append(next_version)
            current = next_version

        return list(reversed(versions))  # от новой к старой

    @property
    def version_count(self):
        """Количество версий"""
        return len(self.version_history)

    # ═══════════════════════════════════════════════════════════════
    # СТАТИЧЕСКИЕ МЕТОДЫ
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def sanitize_folder_name(name):
        """
        Нормализация имени для папки на диске.
        Убирает спецсимволы, заменяет пробелы на _, обрезает до 100 символов.
        """
        # Убираем символы, недопустимые в путях Windows/Linux
        sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
        # Пробелы → подчёркивания
        sanitized = re.sub(r'\s+', '_', sanitized.strip())
        # Убираем двойные подчёркивания
        sanitized = re.sub(r'_+', '_', sanitized)
        # Обрезаем
        return sanitized[:100] or 'unnamed'

    @staticmethod
    def get_upload_path(category, file_type, **kwargs):
        """
        Генерирует относительный путь для загрузки файла.

        kwargs может содержать:
        - sample: объект Sample (для SAMPLE)
        - acceptance_act: объект AcceptanceAct (для CLIENT/ACT_*)
        - contract: объект Contract (для CLIENT/CONTRACT_*)
        - equipment: объект Equipment (для EQUIPMENT)
        - standard: объект Standard (для STANDARD)
        - user: объект User (для PERSONAL)
        """
        from datetime import date

        # Получаем дефолтную подпапку
        try:
            defaults = FileTypeDefault.objects.get(
                category=category, file_type=file_type
            )
            subfolder = defaults.default_subfolder
        except FileTypeDefault.DoesNotExist:
            subfolder = ''

        year = str(date.today().year)

        if category == FileCategory.SAMPLE:
            sample = kwargs.get('sample')
            if sample:
                lab_code = sample.laboratory.code if sample.laboratory else 'UNKNOWN'
                seq = str(sample.sequence_number).zfill(3)
                parts = ['samples', lab_code, year, seq]
            else:
                parts = ['samples', '_unlinked', year]

        elif category == FileCategory.CLIENT:
            act = kwargs.get('acceptance_act')
            contract = kwargs.get('contract')

            if act:
                client_name = File.sanitize_folder_name(
                    act.contract.client.name if act.contract and act.contract.client else 'unknown'
                )
                doc_number = File.sanitize_folder_name(act.doc_number or str(act.id))
                parts = ['clients', client_name, 'acts', doc_number]
            elif contract:
                client_name = File.sanitize_folder_name(
                    contract.client.name if contract.client else 'unknown'
                )
                contract_num = File.sanitize_folder_name(contract.number)
                parts = ['clients', client_name, 'contracts', contract_num]
            else:
                parts = ['clients', '_unlinked', year]

        elif category == FileCategory.EQUIPMENT:
            equipment = kwargs.get('equipment')
            if equipment:
                eq_name = File.sanitize_folder_name(equipment.name)
                parts = ['equipment', eq_name]
            else:
                parts = ['equipment', '_unlinked']

        elif category == FileCategory.STANDARD:
            standard = kwargs.get('standard')
            if standard:
                std_code = File.sanitize_folder_name(standard.code)
                parts = ['standards', std_code]
            else:
                parts = ['standards', '_unlinked']

        elif category == FileCategory.QMS:
            parts = ['qms']

        elif category == FileCategory.PERSONAL:
            user = kwargs.get('user')
            if user:
                folder_name = f'{user.id}_{File.sanitize_folder_name(user.username)}'
                parts = ['personal', folder_name]
            else:
                parts = ['personal', '_unknown']

        elif category == FileCategory.INBOX:
            parts = ['inbox', str(date.today())]

        else:
            parts = ['other', year]

        # Добавляем подпапку из file_type_defaults
        if subfolder:
            parts.append(subfolder)

        return os.path.join(*parts)

    @staticmethod
    def get_default_visibility(category, file_type):
        """Получает дефолтную видимость для типа файла"""
        try:
            defaults = FileTypeDefault.objects.get(
                category=category, file_type=file_type
            )
            return defaults.default_visibility
        except FileTypeDefault.DoesNotExist:
            return FileVisibility.ALL


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ МОДЕЛИ
# =============================================================================

class FileTypeDefault(models.Model):
    """Дефолтные настройки для типов файлов"""
    category = models.CharField(max_length=50, verbose_name='Категория')
    file_type = models.CharField(max_length=50, verbose_name='Тип файла')
    default_visibility = models.CharField(
        max_length=20, default=FileVisibility.ALL,
        verbose_name='Видимость по умолчанию'
    )
    default_subfolder = models.CharField(
        max_length=200, default='', blank=True,
        verbose_name='Подпапка'
    )

    class Meta:
        db_table = 'file_type_defaults'
        managed = False
        unique_together = [('category', 'file_type')]
        verbose_name = 'Настройка типа файла'
        verbose_name_plural = 'Настройки типов файлов'

    def __str__(self):
        return f'{self.category}/{self.file_type}'


class FileVisibilityRule(models.Model):
    """Правила скрытия файлов от ролей (blacklist)"""
    file_type = models.CharField(max_length=50, verbose_name='Тип файла')
    category = models.CharField(max_length=50, verbose_name='Категория')
    role = models.CharField(max_length=50, verbose_name='Роль (запрет)')

    class Meta:
        db_table = 'file_visibility_rules'
        managed = False
        unique_together = [('file_type', 'category', 'role')]
        verbose_name = 'Правило видимости'
        verbose_name_plural = 'Правила видимости'

    def __str__(self):
        return f'{self.category}/{self.file_type} → скрыт от {self.role}'


class PersonalFolderAccess(models.Model):
    """Доступ к личным папкам"""
    owner = models.ForeignKey(
        'User', on_delete=models.CASCADE,
        related_name='folder_grants_given',
        db_column='owner_id',
        verbose_name='Владелец'
    )
    granted_to = models.ForeignKey(
        'User', on_delete=models.CASCADE,
        related_name='folder_grants_received',
        db_column='granted_to_id',
        verbose_name='Доступ для'
    )
    access_level = models.CharField(
        max_length=10, default='VIEW',
        verbose_name='Уровень доступа'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        db_table = 'personal_folder_access'
        managed = False
        unique_together = [('owner', 'granted_to')]
        verbose_name = 'Доступ к личной папке'
        verbose_name_plural = 'Доступы к личным папкам'

    def __str__(self):
        return f'{self.owner} → {self.granted_to} ({self.access_level})'