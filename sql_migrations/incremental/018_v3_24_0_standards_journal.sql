-- ============================================================================
-- CISIS v3.24.0 — Журнал справочника стандартов
-- Файл: sql_migrations/incremental/018_v3_24_0_standards_journal.sql
-- Дата: 4 марта 2026
-- ============================================================================

-- 1. Добавляем журнал
INSERT INTO journals (code, name, is_active)
VALUES ('STANDARDS', 'Справочник стандартов', TRUE)
ON CONFLICT (code) DO NOTHING;

-- 2. Добавляем столбец доступа
INSERT INTO journal_columns (journal_id, code, name, display_order, is_active)
VALUES (
    (SELECT id FROM journals WHERE code = 'STANDARDS'),
    'access', 'Доступ', 1, TRUE
)
ON CONFLICT DO NOTHING;

-- 3. Права по ролям
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT v.role, j.id, jc.id, v.access_level
FROM (VALUES
    ('CEO',              'EDIT'),
    ('CTO',              'EDIT'),
    ('SYSADMIN',         'EDIT'),
    ('QMS_HEAD',         'EDIT'),
    ('QMS_ADMIN',        'EDIT'),
    ('LAB_HEAD',         'EDIT'),
    ('CLIENT_MANAGER',   'VIEW'),
    ('CLIENT_DEPT_HEAD', 'VIEW'),
    ('TESTER',           'VIEW'),
    ('METROLOGIST',      'VIEW')
) AS v(role, access_level)
CROSS JOIN journals j
CROSS JOIN journal_columns jc
WHERE j.code = 'STANDARDS'
  AND jc.journal_id = j.id
  AND jc.code = 'access'
ON CONFLICT DO NOTHING;
