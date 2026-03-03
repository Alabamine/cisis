"""
Views разделены на модули по функциональности.

Этот файл позволяет импортировать все view-функции как раньше:
    from core.views import manage_permissions, journal_samples

⭐ v3.13.0: sample_views.py разделён на модули:
    constants.py, field_utils.py, freeze_logic.py, save_logic.py,
    journal_views.py, sample_views.py, views.py
"""

# Управление правами
from .permissions_views import manage_permissions

# ⭐ v3.13.0: Общие views (были в sample_views.py)
from .views import (
    workspace_home,
    logout_view,
)

# Работа с образцами (⭐ v3.13.0: sample_create, sample_detail остались в sample_views)
from .sample_views import (
    sample_detail,
    sample_create,
    unfreeze_registration_block,
    search_protocols,
    search_standards,
)

# ⭐ v3.13.0: Журнал (был в sample_views.py)
from .journal_views import (
    journal_samples,
    export_journal_xlsx,
    journal_filter_options,
    save_column_preferences,
)

# Проверка регистрации и протоколов
from .verification_views import (
    verify_sample,
    verify_protocol,
)

# Работа с файлами
from .file_views import (
      file_upload,
      file_download,
      file_thumbnail,
      file_delete,
      file_replace,
      api_file_types,
      api_entity_files,
)

# API эндпоинты
from .api_views import (
    get_client_contracts,
)

from .auth_views import workspace_login

__all__ = [
    # Управление правами
    'manage_permissions',

    # Общие
    'workspace_home',
    'logout_view',

    # Образцы
    'sample_detail',
    'sample_create',
    'unfreeze_registration_block',
    'search_protocols',
    'search_standards',

    # Журнал
    'journal_samples',
    'export_journal_xlsx',
    'journal_filter_options',
    'save_column_preferences',

    # Проверка
    'verify_sample',
    'verify_protocol',

    # Файлы
      'file_upload',
      'file_download',
      'file_thumbnail',
      'file_delete',
      'file_replace',
      'api_file_types',
      'api_entity_files',

    # API
    'get_client_contracts',
]

from .audit_views import audit_log_view

from . import parameter_views