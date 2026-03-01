-- ============================================================
-- CISIS v3.22.0 — Пул показателей по стандарту
-- Миграция: 014_v3_22_0_parameters.sql
-- Дата: 1 марта 2026
-- ============================================================

BEGIN;

-- ============================================================
-- 1. Таблица parameters — единый справочник показателей
-- ============================================================
CREATE TABLE IF NOT EXISTS parameters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    unit VARCHAR(50),
    description TEXT,
    category VARCHAR(50) NOT NULL DEFAULT 'OTHER',
        -- MECHANICAL, THERMAL, CHEMICAL, DIMENSIONAL, OTHER
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_parameters_name_unit UNIQUE (name, unit)
);

COMMENT ON TABLE parameters IS 'Единый справочник определяемых показателей';
COMMENT ON COLUMN parameters.category IS 'MECHANICAL / THERMAL / CHEMICAL / DIMENSIONAL / OTHER';

CREATE INDEX idx_parameters_category ON parameters (category) WHERE is_active = TRUE;
CREATE INDEX idx_parameters_name ON parameters (name);

-- ============================================================
-- 2. Таблица standard_parameters — привязка показателя к стандарту
-- ============================================================
CREATE TABLE IF NOT EXISTS standard_parameters (
    id SERIAL PRIMARY KEY,
    standard_id INT NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    parameter_id INT NOT NULL REFERENCES parameters(id) ON DELETE CASCADE,
    parameter_role VARCHAR(20) NOT NULL DEFAULT 'PRIMARY',
        -- PRIMARY / AUXILIARY / CALCULATED
    is_default BOOLEAN NOT NULL DEFAULT TRUE,
    unit_override VARCHAR(50),
    test_conditions VARCHAR(500),
    precision INT,
    report_group VARCHAR(100),
    report_order INT NOT NULL DEFAULT 0,
    display_order INT NOT NULL DEFAULT 0,
    formula TEXT,
    depends_on JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_standard_parameter UNIQUE (standard_id, parameter_id),
    CONSTRAINT chk_parameter_role CHECK (parameter_role IN ('PRIMARY', 'AUXILIARY', 'CALCULATED'))
);

COMMENT ON TABLE standard_parameters IS 'Привязка показателей к стандартам с настройками';
COMMENT ON COLUMN standard_parameters.parameter_role IS 'PRIMARY — основной, AUXILIARY — вспомогательный, CALCULATED — расчётный';
COMMENT ON COLUMN standard_parameters.is_default IS 'Автоматически включать при выборе стандарта';
COMMENT ON COLUMN standard_parameters.unit_override IS 'Если единица отличается от parameters.unit';
COMMENT ON COLUMN standard_parameters.report_group IS 'Группа в протоколе (Механические, Размеры и т.д.)';
COMMENT ON COLUMN standard_parameters.formula IS 'Формула расчёта для CALCULATED (будущее)';
COMMENT ON COLUMN standard_parameters.depends_on IS 'JSON-массив parameter_id для CALCULATED (будущее)';

CREATE INDEX idx_std_params_standard ON standard_parameters (standard_id) WHERE is_active = TRUE;
CREATE INDEX idx_std_params_parameter ON standard_parameters (parameter_id);

-- ============================================================
-- 3. Таблица sample_parameters — показатели конкретного образца
-- ============================================================
CREATE TABLE IF NOT EXISTS sample_parameters (
    id SERIAL PRIMARY KEY,
    sample_id INT NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    standard_parameter_id INT REFERENCES standard_parameters(id) ON DELETE SET NULL,
        -- NULL для кастомных показателей
    custom_name VARCHAR(255),
    custom_unit VARCHAR(50),
    is_selected BOOLEAN NOT NULL DEFAULT TRUE,
        -- TRUE = показывается в «определяемых параметрах»
    display_order INT NOT NULL DEFAULT 0,

    -- Задел на результаты (всё NULL пока)
    result_numeric DECIMAL(15, 6),
    result_text VARCHAR(500),
    result_status VARCHAR(20),
        -- PENDING / FILLED / VALIDATED
    tested_by_id INT REFERENCES users(id) ON DELETE SET NULL,
    tested_at TIMESTAMPTZ,
    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Один показатель-стандарт на образец (кастомные не попадают под constraint)
    CONSTRAINT uq_sample_std_parameter UNIQUE (sample_id, standard_parameter_id),
    CONSTRAINT chk_custom_or_standard CHECK (
        standard_parameter_id IS NOT NULL OR custom_name IS NOT NULL
    )
);

COMMENT ON TABLE sample_parameters IS 'Показатели конкретного образца (выбранные из стандарта или кастомные)';
COMMENT ON COLUMN sample_parameters.is_selected IS 'TRUE — виден в поле «определяемые параметры», FALSE — только в таблице результатов';
COMMENT ON COLUMN sample_parameters.result_status IS 'PENDING / FILLED / VALIDATED (будущее)';

CREATE INDEX idx_sample_params_sample ON sample_parameters (sample_id);
CREATE INDEX idx_sample_params_std_param ON sample_parameters (standard_parameter_id) WHERE standard_parameter_id IS NOT NULL;
CREATE INDEX idx_sample_params_selected ON sample_parameters (sample_id) WHERE is_selected = TRUE;

-- ============================================================
-- 4. Столбец parameters_management в journal_columns (журнал SAMPLES)
-- ============================================================
INSERT INTO journal_columns (journal_id, code, name, display_order)
SELECT j.id, 'parameters_management', 'Управление показателями', 900
FROM journals j
WHERE j.code = 'SAMPLES'
AND NOT EXISTS (
    SELECT 1 FROM journal_columns jc
    WHERE jc.journal_id = j.id AND jc.code = 'parameters_management'
);

-- ============================================================
-- 5. Права: parameters_management для ролей
-- ============================================================
-- EDIT: CEO, CTO, SYSADMIN, QMS_HEAD, QMS_ADMIN, LAB_HEAD
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT r.role, jc.journal_id, jc.id, 'EDIT'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id
CROSS JOIN (
    VALUES ('CEO'), ('CTO'), ('SYSADMIN'), ('QMS_HEAD'), ('QMS_ADMIN'), ('LAB_HEAD')
) AS r(role)
WHERE j.code = 'SAMPLES' AND jc.code = 'parameters_management'
AND NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role = r.role AND rp.column_id = jc.id
);

-- VIEW: CLIENT_MANAGER, CLIENT_DEPT_HEAD, TESTER, METROLOGIST
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT r.role, jc.journal_id, jc.id, 'VIEW'
FROM journal_columns jc
JOIN journals j ON j.id = jc.journal_id
CROSS JOIN (
    VALUES ('CLIENT_MANAGER'), ('CLIENT_DEPT_HEAD'), ('TESTER'), ('METROLOGIST')
) AS r(role)
WHERE j.code = 'SAMPLES' AND jc.code = 'parameters_management'
AND NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role = r.role AND rp.column_id = jc.id
);

COMMIT;
