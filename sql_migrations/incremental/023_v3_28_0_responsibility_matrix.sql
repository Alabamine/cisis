-- ============================================================
-- CISIS v3.28.0 — Матрица ответственности + исключения по стандартам
-- Файл: sql_migrations/incremental/023_v3_28_0_responsibility_matrix.sql
-- ============================================================

BEGIN;

-- =============================================================
-- 1. Таблица допуска сотрудников к областям аккредитации
-- =============================================================

CREATE TABLE IF NOT EXISTS user_accreditation_areas (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accreditation_area_id INTEGER NOT NULL REFERENCES accreditation_areas(id) ON DELETE CASCADE,
    assigned_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_by_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(user_id, accreditation_area_id)
);

CREATE INDEX IF NOT EXISTS idx_uaa_user ON user_accreditation_areas(user_id);
CREATE INDEX IF NOT EXISTS idx_uaa_area ON user_accreditation_areas(accreditation_area_id);

-- =============================================================
-- 2. Таблица исключений: сотрудник допущен к области,
--    но НЕ к конкретному стандарту в ней
-- =============================================================

CREATE TABLE IF NOT EXISTS user_standard_exclusions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    standard_id     INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    excluded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    excluded_by_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason          VARCHAR(300),
    UNIQUE(user_id, standard_id)
);

CREATE INDEX IF NOT EXISTS idx_use_user ON user_standard_exclusions(user_id);
CREATE INDEX IF NOT EXISTS idx_use_standard ON user_standard_exclusions(standard_id);

-- =============================================================
-- 3. Журнал RESPONSIBILITY_MATRIX
-- =============================================================

INSERT INTO journals (code, name, is_active)
VALUES ('RESPONSIBILITY_MATRIX', 'Матрица ответственности', TRUE)
ON CONFLICT (code) DO NOTHING;

INSERT INTO journal_columns (journal_id, code, name, is_active, display_order)
SELECT j.id, 'access', 'Доступ', TRUE, 0
FROM journals j
WHERE j.code = 'RESPONSIBILITY_MATRIX'
  AND NOT EXISTS (
    SELECT 1 FROM journal_columns jc
    WHERE jc.journal_id = j.id AND jc.code = 'access'
  );

-- =============================================================
-- 4. Права: VIEW для всех ролей, EDIT для CEO/CTO/SYSADMIN/LAB_HEAD
-- =============================================================

DO $$
DECLARE
    j_id INTEGER;
    col_id INTEGER;
    r TEXT;
    view_roles TEXT[] := ARRAY[
        'CEO','CTO','SYSADMIN','LAB_HEAD','TESTER',
        'WORKSHOP_HEAD','WORKSHOP','QMS_HEAD','QMS_ADMIN',
        'CLIENT_MANAGER','CLIENT_DEPT_HEAD','METROLOGIST',
        'CONTRACT_SPEC','ACCOUNTANT','OTHER'
    ];
    edit_roles TEXT[] := ARRAY['CEO','CTO','SYSADMIN','LAB_HEAD'];
BEGIN
    SELECT id INTO j_id FROM journals WHERE code = 'RESPONSIBILITY_MATRIX';
    SELECT id INTO col_id FROM journal_columns WHERE journal_id = j_id AND code = 'access';

    IF j_id IS NOT NULL AND col_id IS NOT NULL THEN
        FOREACH r IN ARRAY view_roles LOOP
            INSERT INTO role_permissions (role, journal_id, column_id, access_level)
            VALUES (r, j_id, col_id, 'VIEW')
            ON CONFLICT (role, journal_id, column_id) DO NOTHING;
        END LOOP;

        FOREACH r IN ARRAY edit_roles LOOP
            UPDATE role_permissions
            SET access_level = 'EDIT'
            WHERE role = r AND journal_id = j_id AND column_id = col_id;
        END LOOP;
    END IF;
END $$;

COMMIT;
