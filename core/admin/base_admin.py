from django.contrib import admin

from core.models import (
    Laboratory,
    Client,
    ClientContact,
    Contract,
    AccreditationArea,
    Standard,
    StandardAccreditationArea,
    Holiday,
    Equipment,
    EquipmentAccreditationArea,
    EquipmentMaintenance,
    StandardLaboratory,        # ⭐ v3.11.2
)
from core.models.parameters import Parameter, StandardParameter, SampleParameter

# ═══════════════════════════════════════════════════════════════
# ИНЛАЙНЫ
# ═══════════════════════════════════════════════════════════════

class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 1


class ContractInline(admin.TabularInline):
    model = Contract
    extra = 1


class StandardAccreditationAreaInline(admin.TabularInline):
    model = StandardAccreditationArea
    extra = 1

class StandardLaboratoryInline(admin.TabularInline):
    model = StandardLaboratory
    extra = 1

class EquipmentAccreditationAreaInline(admin.TabularInline):
    model = EquipmentAccreditationArea
    extra = 1


class EquipmentMaintenanceInline(admin.TabularInline):
    model   = EquipmentMaintenance
    extra   = 1
    ordering = ['-maintenance_date']

class StandardParameterInline(admin.TabularInline):
    model = StandardParameter
    extra = 1
    fields = ('parameter', 'parameter_role', 'is_default', 'unit_override',
              'test_conditions', 'precision', 'display_order')
# ═══════════════════════════════════════════════════════════════
# МОДЕЛИ
# ═══════════════════════════════════════════════════════════════

@admin.register(Laboratory)
class LaboratoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'head', 'is_active']
    list_filter  = ['is_active']
    search_fields = ['name', 'code']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display  = ['name', 'inn', 'is_active']
    list_filter   = ['is_active']
    search_fields = ['name', 'inn']
    inlines       = [ClientContactInline, ContractInline]


@admin.register(AccreditationArea)
class AccreditationAreaAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'is_default']
    list_filter  = ['is_active']

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['date', 'name', 'is_working']
    list_filter  = ['is_working']
    ordering     = ['-date']


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display  = ['accounting_number', 'name', 'equipment_type', 'laboratory', 'status']
    list_filter   = ['equipment_type', 'status', 'ownership', 'laboratory']
    search_fields = ['accounting_number', 'name', 'inventory_number']
    inlines       = [EquipmentAccreditationAreaInline, EquipmentMaintenanceInline]

@admin.register(Standard)
class StandardAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'test_code', 'test_type', 'is_active']
    list_filter   = ['is_active']
    search_fields = ['code', 'name', 'test_code']
    inlines       = [StandardAccreditationAreaInline, StandardLaboratoryInline]

@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'category', 'is_active', 'display_order')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'name_en')
    ordering = ('display_order', 'name')