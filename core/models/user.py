"""
Модель пользователя и связанные классы
"""

from django.db import models


# =============================================================================
# РОЛИ ПОЛЬЗОВАТЕЛЕЙ
# =============================================================================

class UserRole(models.TextChoices):
    # Руководство
    CEO = 'CEO', 'Генеральный директор'
    CTO = 'CTO', 'Технический директор'
    SYSADMIN = 'SYSADMIN', 'Системный администратор'

    # Лаборатории
    LAB_HEAD = 'LAB_HEAD', 'Заведующий лабораторией'
    TESTER = 'TESTER', 'Испытатель'

    # Отдел по работе с заказчиками (регистрация образцов)
    CLIENT_DEPT_HEAD = 'CLIENT_DEPT_HEAD', 'Руководитель отдела по работе с заказчиками'
    CLIENT_MANAGER = 'CLIENT_MANAGER', 'Специалист по работе с заказчиками'
    CONTRACT_SPEC = 'CONTRACT_SPEC', 'Специалист по договорам'

    # СМК (проверка протоколов)
    QMS_HEAD = 'QMS_HEAD', 'Руководитель СМК'
    QMS_ADMIN = 'QMS_ADMIN', 'Администратор СМК'
    METROLOGIST = 'METROLOGIST', 'Метролог'

    # ⭐ v3.9.0: Мастерская — самостоятельное подразделение
    WORKSHOP_HEAD = 'WORKSHOP_HEAD', 'Начальник мастерской'
    WORKSHOP = 'WORKSHOP', 'Сотрудник мастерской'

    # Бухгалтерия
    ACCOUNTANT = 'ACCOUNTANT', 'Бухгалтер'

    # Прочие
    OTHER = 'OTHER', 'Прочий'


# =============================================================================
# МЕНЕДЖЕР МОДЕЛИ USER
# =============================================================================

class UserManager(models.Manager):
    def get_by_natural_key(self, username):
        return self.get(username=username)


# =============================================================================
# ДОПОЛНИТЕЛЬНЫЕ ЛАБОРАТОРИИ (промежуточная таблица)
# =============================================================================
# managed=False — таблица создаётся через SQL-миграцию вручную
# =============================================================================

class UserAdditionalLaboratory(models.Model):
    """Промежуточная таблица: дополнительные лаборатории пользователя."""
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        db_column='user_id',
    )
    laboratory = models.ForeignKey(
        'Laboratory',
        on_delete=models.CASCADE,
        db_column='laboratory_id',
    )

    class Meta:
        db_table = 'user_additional_laboratories'
        managed = False
        unique_together = ('user', 'laboratory')
        verbose_name = 'Дополнительная лаборатория'
        verbose_name_plural = 'Дополнительные лаборатории'

    def __str__(self):
        return f'{self.user} → {self.laboratory}'


# =============================================================================
# МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ
# =============================================================================
# Собственная модель пользователя — НЕ наследуем от AbstractUser,
# потому что таблица users уже существует со своей схемой.
# Для аутентификации через Django используем custom backend.
# =============================================================================

class User(models.Model):
    username       = models.CharField(max_length=100, unique=True)
    password_hash  = models.CharField(max_length=255)
    email          = models.CharField(max_length=255, default='', blank=True)
    first_name     = models.CharField('Имя', max_length=100, default='', blank=True)
    sur_name       = models.CharField('Отчество', max_length=100, default='', blank=True)
    last_name      = models.CharField('Фамилия', max_length=100, default='', blank=True)
    role           = models.CharField(max_length=20, default=UserRole.OTHER, choices=UserRole.choices)
    laboratory     = models.ForeignKey(
        'Laboratory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    is_active      = models.BooleanField(default=True)
    is_staff       = models.BooleanField(default=False)
    is_superuser   = models.BooleanField(default=False)
    ui_preferences = models.JSONField(default=dict, blank=True)
    last_login     = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    # ⭐ v3.8.0: Стажёр и наставник
    is_trainee     = models.BooleanField(default=False, verbose_name='Стажёр')
    mentor         = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trainees',
        verbose_name='Наставник',
    )

    # ⭐ v3.8.0: Дополнительные лаборатории (через промежуточную таблицу)
    additional_laboratories = models.ManyToManyField(
        'Laboratory',
        through='UserAdditionalLaboratory',
        related_name='additional_users',
        blank=True,
        verbose_name='Дополнительные лаборатории',
    )

    objects = UserManager()

    # Обязательные атрибуты для Django auth
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'users'
        managed  = False
        ordering = ['last_name', 'first_name']
        verbose_name        = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        parts = [self.last_name, self.first_name, self.sur_name]
        full = ' '.join(p for p in parts if p)
        return f'{full} ({self.username})'


    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.sur_name]
        return ' '.join(p for p in parts if p)

    # ═══════════════════════════════════════════════════════════════
    # ⭐ v3.8.0: РАБОТА С ЛАБОРАТОРИЯМИ
    # ═══════════════════════════════════════════════════════════════

    @property
    def all_laboratories(self):
        """
        Возвращает set всех лабораторий пользователя
        (основная + дополнительные).
        """
        labs = set()
        if self.laboratory:
            labs.add(self.laboratory)
        try:
            labs.update(self.additional_laboratories.all())
        except Exception:
            pass
        return labs

    @property
    def all_laboratory_ids(self):
        """
        Возвращает set ID всех лабораторий пользователя.
        Удобно для фильтрации queryset через laboratory_id__in.
        """
        ids = set()
        if self.laboratory_id:
            ids.add(self.laboratory_id)
        try:
            ids.update(
                self.additional_laboratories.values_list('id', flat=True)
            )
        except Exception:
            pass
        return ids

    def has_laboratory(self, laboratory):
        """
        Проверяет, относится ли пользователь к данной лаборатории
        (основная или дополнительная).
        """
        if self.laboratory_id and self.laboratory_id == laboratory.id:
            return True
        try:
            return self.additional_laboratories.filter(id=laboratory.id).exists()
        except Exception:
            return False

    # ═══════════════════════════════════════════════════════════════
    # ⭐ v3.9.0: ПРОВЕРКА РОЛИ МАСТЕРСКОЙ
    # ═══════════════════════════════════════════════════════════════

    @property
    def is_workshop_role(self):
        """Проверяет, является ли пользователь сотрудником мастерской (любая роль)."""
        return self.role in (UserRole.WORKSHOP_HEAD, UserRole.WORKSHOP)

    @property
    def is_workshop_head(self):
        """Проверяет, является ли пользователь начальником мастерской."""
        return self.role == UserRole.WORKSHOP_HEAD

    # ═══════════════════════════════════════════════════════════════
    # ⭐ v3.8.0: ВАЛИДАЦИЯ СТАЖЁРА
    # ═══════════════════════════════════════════════════════════════

    def clean(self):
        """Валидация модели перед сохранением."""
        from django.core.exceptions import ValidationError

        if self.is_trainee and not self.mentor_id:
            raise ValidationError({
                'mentor': 'Для стажёра обязательно указать наставника.'
            })

        if self.mentor_id and self.mentor_id == self.pk:
            raise ValidationError({
                'mentor': 'Пользователь не может быть наставником самому себе.'
            })

        if self.mentor_id:
            try:
                mentor_user = User.objects.get(pk=self.mentor_id)
                if mentor_user.is_trainee:
                    raise ValidationError({
                        'mentor': 'Наставник не может быть стажёром.'
                    })
                # Наставник должен быть из того же подразделения
                if (self.laboratory_id
                        and mentor_user.laboratory_id
                        and self.laboratory_id != mentor_user.laboratory_id):
                    raise ValidationError({
                        'mentor': 'Наставник должен быть из того же подразделения.'
                    })
            except User.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        # Если is_trainee снят — очищаем наставника
        if not self.is_trainee:
            self.mentor = None
        super().save(*args, **kwargs)

    # ═══════════════════════════════════════════════════════════════
    # МЕТОДЫ ДЛЯ РАБОТЫ С ПАРОЛЯМИ
    # ═══════════════════════════════════════════════════════════════

    def check_password(self, raw_password):
        """Проверяет соответствие пароля хэшу"""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password_hash)

    def set_password(self, raw_password):
        """Устанавливает новый пароль"""
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw_password)

    # ═══════════════════════════════════════════════════════════════
    # ИНТЕРФЕЙС ДЛЯ DJANGO AUTH BACKEND
    # ═══════════════════════════════════════════════════════════════

    @property
    def is_authenticated(self):
        """Django ожидает этот атрибут у объекта user"""
        return True

    @property
    def is_anonymous(self):
        """Django ожидает этот атрибут у объекта user"""
        return False

    def has_perm(self, perm, obj=None):
        """Проверка прав. SYSADMIN и суперпользователи имеют все права."""
        if self.is_superuser or self.role == UserRole.SYSADMIN:
            return True

        # Для остальных — базовый доступ если is_staff
        return self.is_active and self.is_staff

    def has_module_perms(self, app_label):
        """Проверка прав к приложению."""
        if self.is_superuser or self.role == UserRole.SYSADMIN:
            return True

        # ⭐ v3.9.0: WORKSHOP_HEAD добавлен в список ролей с доступом к админке
        allowed_roles = ['SYSADMIN', 'QMS_HEAD', 'LAB_HEAD', 'WORKSHOP_HEAD']
        if self.role in allowed_roles and self.is_active and self.is_staff:
            return True

        # Остальные роли не имеют доступа ни к каким модулям админки
        return False

    # ═══════════════════════════════════════════════════════════════
    # ЗАЩИТА ОТ УДАЛЕНИЯ
    # ═══════════════════════════════════════════════════════════════

    def delete(self, *args, **kwargs):
        """
        БЛОКИРУЕМ удаление пользователей!
        Вместо удаления используйте деактивацию.
        """
        raise PermissionError(
            f'Удаление пользователей запрещено! '
            f'Используйте деактивацию: user.is_active = False'
        )

    def deactivate(self, reason=''):
        """
        Безопасная деактивация вместо удаления
        """
        from django.utils import timezone

        self.is_active = False
        if hasattr(self, 'termination_date'):
            self.termination_date = timezone.now().date()
        if hasattr(self, 'termination_reason'):
            self.termination_reason = reason
        self.save()

        return f'Пользователь {self.full_name} деактивирован'