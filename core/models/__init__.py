"""
Модуль models разделён на логические группы для упрощения работы.

Импортируем всё здесь, чтобы Django и остальной код видел модели как раньше:
    from core.models import Sample, User, Laboratory  # работает!
"""

# ВАЖНО: Порядок импортов имеет значение из-за зависимостей между моделями

# 1. Сначала валидаторы (не зависят ни от чего)
from .base import validate_latin_only

# 2. Базовые справочники (минимум зависимостей)
from .base import (
    Laboratory,
    DepartmentType,           # ⭐ v3.17.0
    RoleLaboratoryAccess,     # ⭐ v3.17.0
    Client,
    ClientContact,
    Contract,
    ContractStatus,
    AccreditationArea,
    Standard,
    StandardAccreditationArea,
    Holiday,
    StandardLaboratory,
)

# 3. Пользователи (зависят от Laboratory)
from .user import (
    User,
    UserRole,
    UserAdditionalLaboratory,  # ⭐ v3.8.0
)

# 4. Оборудование (зависит от Laboratory, User, AccreditationArea)
from .equipment import (
    Equipment,
    EquipmentType,
    EquipmentStatus,
    EquipmentAccreditationArea,
    EquipmentMaintenance,
    MaintenanceType,
    EquipmentMaintenancePlan,   # ⭐ v3.24.0
    EquipmentMaintenanceLog,    # ⭐ v3.24.0
    MaintenanceFrequencyUnit,   # ⭐ v3.24.0
    MaintenanceLogStatus,       # ⭐ v3.24.0
    VerificationResult,         # ⭐ v3.29.0
)

# 5. Образцы (зависят от всех предыдущих)
from .sample import (
    Sample,
    SampleStatus,
    ReportType,
    SampleStandard,  # ⭐ v3.13.0
    WorkshopStatus,
    FurtherMovement,
    SampleMeasuringInstrument,
    SampleTestingEquipment,
    SampleOperator,
    SampleManufacturingMeasuringInstrument,
    SampleManufacturingTestingEquipment,
    SampleManufacturingOperator,
    SampleManufacturingAuxiliaryEquipment,   # ⭐ v3.10.1
    SampleAuxiliaryEquipment,
)

# 6. Система прав доступа (зависит от User)
from .permissions import (
    Journal,
    JournalColumn,
    RolePermission,
    UserPermissionOverride,
    PermissionsLog,
    AccessLevel,
    PermissionType,
)

# 7. Журналы логов (зависят от Sample, User, Equipment, Laboratory)
from .logs import (
    ClimateLog,
    WeightLog,
    WorkshopLog,
    TimeLog,
)

# 8. Файлы (зависят от Sample, User)
from .files import File, FileTypeDefault, FileVisibilityRule, PersonalFolderAccess

from .parameters import Parameter, StandardParameter, SampleParameter

# ═══════════════════════════════════════════════════════════════════
# __all__ — явно указываем что экспортируется при "from core.models import *"
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    # Валидаторы
    'validate_latin_only',

    # Базовые справочники
    'Laboratory',
    'DepartmentType',           # ⭐ v3.17.0
    'RoleLaboratoryAccess',     # ⭐ v3.17.0
    'Client',
    'ClientContact',
    'Contract',
    'ContractStatus',
    'AccreditationArea',
    'Standard',
    'StandardAccreditationArea',
    'Holiday',
    'StandardLaboratory',

    # Пользователи
    'User',
    'UserRole',
    'UserAdditionalLaboratory',  # ⭐ v3.8.0

    # Оборудование
    'Equipment',
    'EquipmentType',
    'EquipmentStatus',
    'EquipmentAccreditationArea',
    'EquipmentMaintenance',
    'MaintenanceType',
    'EquipmentMaintenancePlan',   # ⭐ v3.24.0
    'EquipmentMaintenanceLog',    # ⭐ v3.24.0
    'MaintenanceFrequencyUnit',   # ⭐ v3.24.0
    'MaintenanceLogStatus',       # ⭐ v3.24.0

    # Образцы
    'Sample',
    'SampleStatus',
    'ReportType',
    'WorkshopStatus',
    'FurtherMovement',
    'SampleMeasuringInstrument',
    'SampleTestingEquipment',
    'SampleOperator',
    'SampleManufacturingMeasuringInstrument',
    'SampleManufacturingTestingEquipment',
    'SampleManufacturingOperator',
    'SampleManufacturingAuxiliaryEquipment',  # ⭐ v3.10.1
    'SampleAuxiliaryEquipment',               # ⭐ v3.10.1

    # Система прав
    'Journal',
    'JournalColumn',
    'RolePermission',
    'UserPermissionOverride',
    'PermissionsLog',
    'AccessLevel',
    'PermissionType',

    # Журналы
    'ClimateLog',
    'WeightLog',
    'WorkshopLog',
    'TimeLog',

    # Файлы
    'File',
    'FileTypeDefault',
    'FileVisibilityRule',
    'PersonalFolderAccess',

    # Параметры
    'Parameter',
    'StandardParameter',
    'SampleParameter',
]

from .audit_log import AuditLog
from .acts import AcceptanceAct, AcceptanceActLaboratory