-- ============================================================
-- Миграция: 019_v3_25_0_analytics_journal.sql
-- Версия:   v3.25.0
-- Дата:     2026-03-05
-- Описание: Журнал ANALYTICS — страница аналитики
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. Журнал ANALYTICS
-- ------------------------------------------------------------
INSERT INTO journals (code, name,  is_active)
SELECT 'ANALYTICS', 'Аналитика',  TRUE
WHERE NOT EXISTS (SELECT 1 FROM journals WHERE code = 'ANALYTICS');

-- ------------------------------------------------------------
-- 2. Столбец access
-- ------------------------------------------------------------
INSERT INTO journal_columns (journal_id, code, name, display_order, is_active)
SELECT
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    'access',
    'Доступ к разделу',
    1,
    TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM journal_columns
    WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND code = 'access'
);

-- ------------------------------------------------------------
-- 3. Права по ролям — EDIT
-- ------------------------------------------------------------
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'CEO',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'EDIT'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'CEO'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'CTO',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'EDIT'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'CTO'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'SYSADMIN',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'EDIT'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'SYSADMIN'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

-- ------------------------------------------------------------
-- 4. Права по ролям — VIEW
-- ------------------------------------------------------------
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'QMS_HEAD',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'VIEW'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'QMS_HEAD'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'QMS_ADMIN',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'VIEW'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'QMS_ADMIN'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'LAB_HEAD',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'VIEW'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'LAB_HEAD'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'METROLOGIST',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'VIEW'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'METROLOGIST'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'CLIENT_DEPT_HEAD',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'VIEW'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'CLIENT_DEPT_HEAD'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

-- ------------------------------------------------------------
-- 5. Права по ролям — NONE
-- ------------------------------------------------------------
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'CLIENT_MANAGER',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'CLIENT_MANAGER'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'TESTER',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'TESTER'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'WORKSHOP_HEAD',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'WORKSHOP_HEAD'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'WORKSHOP',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'WORKSHOP'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'CONTRACT_SPEC',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'CONTRACT_SPEC'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'ACCOUNTANT',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'ACCOUNTANT'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT 'OTHER',
    (SELECT id FROM journals WHERE code = 'ANALYTICS'),
    (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access'),
    'NONE'
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions
    WHERE role = 'OTHER'
      AND journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS')
      AND column_id  = (SELECT id FROM journal_columns WHERE journal_id = (SELECT id FROM journals WHERE code = 'ANALYTICS') AND code = 'access')
);

COMMIT;
