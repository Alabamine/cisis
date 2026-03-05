"""
URL-маршруты для приложения core

⭐ v3.13.0: sample_views.py разделён на модули.
Импорты идут через core.views.__init__ (обратная совместимость).
"""

from django.urls import path
from .views import (
    permissions_views,
    verification_views,
    file_views,
    api_views,
    label_views,
)
# ⭐ v3.13.0: Новые модули — импортируем напрямую для ясности
from .views.views import workspace_home, logout_view
from .views.sample_views import (
        sample_create, sample_detail,
        unfreeze_registration_block,
        search_protocols, search_standards,
        search_moisture_samples,  # ⭐ v3.15.0
    )
from .views.journal_views import (
    journal_samples, export_journal_xlsx,
    journal_filter_options, save_column_preferences,
)
from .views.audit_views import audit_log_view
from .views.bulk_views import bulk_operations
from .views.directory_views import (
    clients_list, client_create, client_edit, client_toggle,
    contract_create, contract_edit, contract_toggle,
    contact_create, contact_edit, contact_delete,
)

from .views.act_views import (
    acts_registry, act_create, act_detail, api_contract_acts,
)

from core.views import parameter_views
from .views.auth_views import workspace_login
from .views.analytics_views import (
    analytics_view, api_laboratories, api_kpi,
    api_monthly_labor, api_laboratory_distribution,
    api_status_distribution, api_daily_registrations,
    api_employee_stats,
)

urlpatterns = [
    path('permissions/', permissions_views.manage_permissions, name='manage_permissions'),
    path('workspace/', workspace_home, name='workspace_home'),
    path('workspace/samples/', journal_samples, name='journal_samples'),
    path('workspace/journal/samples/export/', export_journal_xlsx, name='export_journal_xlsx'),
    path('workspace/samples/filter-options/', journal_filter_options, name='journal_filter_options'),
    path('workspace/samples/save-columns/', save_column_preferences, name='save_column_preferences'),
    path('workspace/samples/bulk/', bulk_operations, name='bulk_operations'),
    path('workspace/samples/create/', sample_create, name='sample_create'),
    path('workspace/samples/<int:sample_id>/', sample_detail, name='sample_detail'),
    # ⭐ v3.12.0: Разморозка блока регистрации
    path('workspace/samples/<int:sample_id>/unfreeze-registration/', unfreeze_registration_block, name='unfreeze_registration'),
    path('workspace/samples/<int:sample_id>/verify/', verification_views.verify_sample, name='verify_sample'),
    path('workspace/samples/<int:sample_id>/verify-protocol/', verification_views.verify_protocol, name='verify_protocol'),
    path('api/search-protocols/', search_protocols, name='search_protocols'),
    path('api/contracts/<int:client_id>/', api_views.get_client_contracts, name='get_client_contracts'),
    path('api/search-standards/', search_standards, name='search_standards'),
    path('api/search-moisture-samples/', search_moisture_samples, name='search_moisture_samples'),  # ⭐ v3.15.0
    path('logout/', logout_view, name='workspace_logout'),
    path('workspace/login/', workspace_login, name='workspace_login'),

    # ⭐ v3.6.0: Генератор этикеток
    path('workspace/labels/', label_views.labels_page, name='labels_page'),
    path('workspace/labels/generate/', label_views.labels_generate, name='labels_generate'),

    path('audit-log/', audit_log_view, name='audit_log'),
    # ⭐ v3.16.0: Справочник заказчиков, договоров и контактов
    path('workspace/clients/', clients_list, name='directory_clients'),
    # ⭐ v3.19.0: Акты приёма-передачи
    path('workspace/acceptance-acts/', acts_registry, name='acts_registry'),
    path('workspace/acceptance-acts/create/', act_create, name='act_create'),
    path('workspace/acceptance-acts/<int:act_id>/', act_detail, name='act_detail'),
    path('api/contracts/<int:contract_id>/acts/', api_contract_acts, name='api_contract_acts'),
    path('workspace/clients/create/', client_create, name='client_create'),
    path('workspace/clients/<int:client_id>/edit/', client_edit, name='client_edit'),
    path('workspace/clients/<int:client_id>/toggle/', client_toggle, name='client_toggle'),
    path('workspace/clients/<int:client_id>/contracts/create/', contract_create, name='contract_create'),
    path('workspace/contracts/<int:contract_id>/edit/', contract_edit, name='contract_edit'),
    path('workspace/contracts/<int:contract_id>/toggle/', contract_toggle, name='contract_toggle'),
    path('workspace/clients/<int:client_id>/contacts/create/', contact_create, name='contact_create'),
    path('workspace/contacts/<int:contact_id>/edit/', contact_edit, name='contact_edit'),
    path('workspace/contacts/<int:contact_id>/delete/', contact_delete, name='contact_delete'),

    # --- Файловая система (v3.21.0) ---
    path('files/upload/', file_views.file_upload, name='file_upload'),
    path('files/<int:file_id>/download/', file_views.file_download, name='file_download'),
    path('files/<int:file_id>/thumbnail/', file_views.file_thumbnail, name='file_thumbnail'),
    path('files/<int:file_id>/delete/', file_views.file_delete, name='file_delete'),
    path('files/<int:file_id>/replace/', file_views.file_replace, name='file_replace'),
    path('api/files/types/<str:category>/', file_views.api_file_types, name='api_file_types'),
    path('api/files/<str:entity_type>/<int:entity_id>/', file_views.api_entity_files, name='api_entity_files'),

    # Справочник стандартов + показатели
    path('workspace/standards/', parameter_views.standards_list, name='standards_list'),
    path('workspace/standards/<int:standard_id>/', parameter_views.standard_detail, name='standard_detail'),

    # AJAX: стандарты
    path('api/standards/save/', parameter_views.api_standard_save, name='api_standard_save'),
    path('api/standards/toggle/', parameter_views.api_standard_toggle, name='api_standard_toggle'),

    # AJAX: показатели (без изменений)
    path('api/parameters/save/', parameter_views.api_parameter_save, name='api_parameter_save'),
    path('api/parameters/delete/', parameter_views.api_parameter_delete, name='api_parameter_delete'),
    path('api/parameters/search/', parameter_views.api_parameter_search, name='api_parameter_search'),
    path('api/parameters/create/', parameter_views.api_parameter_create, name='api_parameter_create'),
    path('api/parameters/reorder/', parameter_views.api_parameter_reorder, name='api_parameter_reorder'),

    # ── Аналитика ──────────────────────────────────────────
    path('workspace/analytics/',
         analytics_view,
         name='analytics'),

    # API-эндпоинты аналитики
    path('workspace/analytics/api/laboratories',
         api_laboratories,
         name='analytics_api_laboratories'),

    path('workspace/analytics/api/kpi',
         api_kpi,
         name='analytics_api_kpi'),

    path('workspace/analytics/api/monthly-labor',
         api_monthly_labor,
         name='analytics_api_monthly_labor'),

    path('workspace/analytics/api/laboratory-distribution',
         api_laboratory_distribution,
         name='analytics_api_lab_distribution'),

    path('workspace/analytics/api/status-distribution',
         api_status_distribution,
         name='analytics_api_status_distribution'),

    path('workspace/analytics/api/daily-registrations',
         api_daily_registrations,
         name='analytics_api_daily_registrations'),

    path('workspace/analytics/api/employee-stats',
         api_employee_stats,
         name='analytics_api_employee_stats'),
]
