-- =============================================================================
-- Миграция: 013_v3_21_0_file_system.sql
-- Версия:   v3.21.0
-- Дата:     28 февраля 2026
-- Описание: Файловая система — таблицы files, file_type_defaults,
--           file_visibility_rules, personal_folder_access.
--           Журнал FILES + столбцы + права.
--           DROP старой таблицы sample_files.
-- =============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. DROP старой таблицы sample_files (данные не нужны)
-- ─────────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS sample_files CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Таблица files (единая для всех файлов системы)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE files (
    id                SERIAL PRIMARY KEY,

    -- Физическое расположение
    file_path         VARCHAR(1000) NOT NULL,
    original_name     VARCHAR(500)  NOT NULL,
    file_size         BIGINT        NOT NULL,
    mime_type         VARCHAR(100)  NOT NULL DEFAULT '',

    -- Категория и тип
    category          VARCHAR(50)   NOT NULL,
    file_type         VARCHAR(50)   NOT NULL DEFAULT '',

    -- Полиморфная привязка (все nullable, максимум одна заполнена)
    sample_id         INTEGER       REFERENCES samples(id)          ON DELETE SET NULL,
    acceptance_act_id INTEGER       REFERENCES acceptance_acts(id)  ON DELETE SET NULL,
    contract_id       INTEGER       REFERENCES contracts(id)        ON DELETE SET NULL,
    equipment_id      INTEGER       REFERENCES equipment(id)        ON DELETE SET NULL,
    standard_id       INTEGER       REFERENCES standards(id)        ON DELETE SET NULL,

    -- Личная папка
    owner_id          INTEGER       REFERENCES users(id)            ON DELETE SET NULL,

    -- Видимость
    visibility        VARCHAR(20)   NOT NULL DEFAULT 'ALL',

    -- Версионность
    version           INTEGER       NOT NULL DEFAULT 1,
    current_version   BOOLEAN       NOT NULL DEFAULT TRUE,
    replaces_id       INTEGER       REFERENCES files(id)            ON DELETE SET NULL,

    -- Превью
    thumbnail_path    VARCHAR(1000) DEFAULT NULL,

    -- Метаданные
    description       VARCHAR(1000) NOT NULL DEFAULT '',
    uploaded_by_id    INTEGER       NOT NULL REFERENCES users(id),
    uploaded_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    is_deleted        BOOLEAN       NOT NULL DEFAULT FALSE,
    deleted_at        TIMESTAMPTZ,
    deleted_by_id     INTEGER       REFERENCES users(id)
);

-- Индексы
CREATE INDEX idx_files_sample      ON files(sample_id)         WHERE sample_id IS NOT NULL;
CREATE INDEX idx_files_act         ON files(acceptance_act_id)  WHERE acceptance_act_id IS NOT NULL;
CREATE INDEX idx_files_contract    ON files(contract_id)        WHERE contract_id IS NOT NULL;
CREATE INDEX idx_files_equipment   ON files(equipment_id)       WHERE equipment_id IS NOT NULL;
CREATE INDEX idx_files_standard    ON files(standard_id)        WHERE standard_id IS NOT NULL;
CREATE INDEX idx_files_owner       ON files(owner_id)           WHERE owner_id IS NOT NULL;
CREATE INDEX idx_files_category    ON files(category);
CREATE INDEX idx_files_active      ON files(is_deleted, current_version)
                                   WHERE is_deleted = FALSE AND current_version = TRUE;
CREATE INDEX idx_files_replaces    ON files(replaces_id)        WHERE replaces_id IS NOT NULL;

-- Constraint: проверка допустимых category
ALTER TABLE files ADD CONSTRAINT chk_files_category
    CHECK (category IN ('SAMPLE', 'CLIENT', 'EQUIPMENT', 'STANDARD', 'QMS', 'PERSONAL', 'INBOX'));

-- Constraint: проверка допустимых visibility
ALTER TABLE files ADD CONSTRAINT chk_files_visibility
    CHECK (visibility IN ('ALL', 'RESTRICTED', 'PRIVATE'));

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Таблица file_type_defaults (дефолты при загрузке)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE file_type_defaults (
    id                  SERIAL PRIMARY KEY,
    category            VARCHAR(50)  NOT NULL,
    file_type           VARCHAR(50)  NOT NULL,
    default_visibility  VARCHAR(20)  NOT NULL DEFAULT 'ALL',
    default_subfolder   VARCHAR(200) NOT NULL DEFAULT '',
    UNIQUE(category, file_type)
);

INSERT INTO file_type_defaults (category, file_type, default_visibility, default_subfolder) VALUES
    ('SAMPLE',    'PHOTO',            'ALL',        'photos'),
    ('SAMPLE',    'RAW_DATA',         'ALL',        'data'),
    ('SAMPLE',    'DRAFT_PROTOCOL',   'ALL',        'drafts'),
    ('SAMPLE',    'PROTOCOL',         'RESTRICTED', 'protocols'),
    ('SAMPLE',    'OTHER',            'ALL',        'other'),
    ('CLIENT',    'CONTRACT_SCAN',    'ALL',        'scans'),
    ('CLIENT',    'CONTRACT_OTHER',   'ALL',        'other'),
    ('CLIENT',    'ACT_SCAN',         'ALL',        'scans'),
    ('CLIENT',    'ACT_FINANCE',      'RESTRICTED', 'finance'),
    ('CLIENT',    'ACT_OTHER',        'ALL',        'other'),
    ('EQUIPMENT', 'MANUAL',           'ALL',        'manuals'),
    ('EQUIPMENT', 'CERTIFICATE',      'ALL',        'certificates'),
    ('EQUIPMENT', 'PASSPORT',         'ALL',        'passports'),
    ('STANDARD',  'PDF',              'ALL',        ''),
    ('STANDARD',  'LINK',             'ALL',        ''),
    ('QMS',       'INSTRUCTION',      'ALL',        'instructions'),
    ('QMS',       'POLICY',           'ALL',        'policies'),
    ('QMS',       'TEMPLATE',         'ALL',        'templates'),
    ('PERSONAL',  'USER_FILE',        'PRIVATE',    ''),
    ('INBOX',     'UNSORTED',         'ALL',        '');

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Таблица file_visibility_rules (blacklist: роли, которым скрыт тип файла)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE file_visibility_rules (
    id          SERIAL PRIMARY KEY,
    file_type   VARCHAR(50) NOT NULL,
    category    VARCHAR(50) NOT NULL,
    role        VARCHAR(50) NOT NULL,
    UNIQUE(file_type, category, role)
);

INSERT INTO file_visibility_rules (file_type, category, role) VALUES
    -- Чистовики протоколов скрыты от исполнителей
    ('PROTOCOL', 'SAMPLE', 'TESTER'),
    ('PROTOCOL', 'SAMPLE', 'WORKSHOP'),
    ('PROTOCOL', 'SAMPLE', 'WORKSHOP_HEAD'),
    -- Финансовые документы актов скрыты от исполнителей мастерской и испытателей
    ('ACT_FINANCE', 'CLIENT', 'TESTER'),
    ('ACT_FINANCE', 'CLIENT', 'WORKSHOP'),
    ('ACT_FINANCE', 'CLIENT', 'WORKSHOP_HEAD');

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Таблица personal_folder_access (доступ к личным папкам)
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE personal_folder_access (
    id              SERIAL PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    granted_to_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_level    VARCHAR(10) NOT NULL DEFAULT 'VIEW',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(owner_id, granted_to_id)
);

ALTER TABLE personal_folder_access ADD CONSTRAINT chk_pfa_access_level
    CHECK (access_level IN ('VIEW', 'EDIT'));

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Журнал FILES + столбцы + права
-- ─────────────────────────────────────────────────────────────────────────────

-- Журнал
INSERT INTO journals (code, name)
VALUES ('FILES', 'Файловый менеджер');

-- Столбцы (для управления доступом по категориям)
INSERT INTO journal_columns (journal_id, code, name, display_order)
SELECT j.id, col.code, col.name, col.display_order
FROM journals j,
(VALUES
    ('samples_files',    'Файлы образцов',             1),
    ('clients_files',    'Файлы клиентов (акты/дог.)', 2),
    ('equipment_files',  'Файлы оборудования',         3),
    ('standards_files',  'Стандарты',                   4),
    ('qms_files',        'Файлы СМК',                  5),
    ('personal_files',   'Личные папки',                6),
    ('inbox_files',      'Входящие (файлопомойка)',     7)
) AS col(code, name, display_order)
WHERE j.code = 'FILES';

-- Права по умолчанию: все роли VIEW на все категории
-- (EDIT будет настраиваться отдельно)
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT r.role, jc.journal_id, jc.id, 'VIEW'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
CROSS JOIN (VALUES
    ('CEO'), ('CTO'), ('SYSADMIN'),
    ('CLIENT_MANAGER'), ('CLIENT_DEPT_HEAD'),
    ('LAB_HEAD'), ('TESTER'),
    ('WORKSHOP'), ('WORKSHOP_HEAD'),
    ('QMS_HEAD'), ('QMS_ADMIN'),
    ('METROLOGIST'), ('CONTRACT_SPEC'), ('ACCOUNTANT')
) AS r(role);

-- Апгрейд до EDIT для управленческих ролей на все категории
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND rp.role IN ('CEO', 'CTO', 'SYSADMIN');

-- EDIT для CLIENT_MANAGER, CLIENT_DEPT_HEAD, CONTRACT_SPEC, ACCOUNTANT на clients_files
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'clients_files'
  AND rp.role IN ('CLIENT_MANAGER', 'CLIENT_DEPT_HEAD', 'CONTRACT_SPEC', 'ACCOUNTANT');

-- EDIT для LAB_HEAD, TESTER на samples_files
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'samples_files'
  AND rp.role IN ('LAB_HEAD', 'TESTER');

-- EDIT для WORKSHOP, WORKSHOP_HEAD на samples_files (фото, данные мастерской)
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'samples_files'
  AND rp.role IN ('WORKSHOP', 'WORKSHOP_HEAD');

-- EDIT для QMS_HEAD, QMS_ADMIN на qms_files и standards_files
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code IN ('qms_files', 'standards_files')
  AND rp.role IN ('QMS_HEAD', 'QMS_ADMIN');

-- EDIT для METROLOGIST на equipment_files
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'equipment_files'
  AND rp.role = 'METROLOGIST';

-- personal_files: EDIT для всех (каждый может загружать в свою папку)
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'personal_files';

-- inbox_files: EDIT для всех (все могут загружать в файлопомойку)
UPDATE role_permissions rp
SET access_level = 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id AND j.code = 'FILES'
WHERE rp.column_id = jc.id
  AND rp.journal_id = jc.journal_id
  AND jc.code = 'inbox_files';

COMMIT;
