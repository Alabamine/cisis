-- ═══════════════════════════════════════════════════════════════
-- CISIS v3.20.0: Добавление столбцов moisture_conditioning,
-- moisture_sample, cutting_standard в journal_columns + права
-- ═══════════════════════════════════════════════════════════════
-- Файл: sql_migrations/incremental/012_v3_20_0_moisture_cutting_columns.sql
-- Дата: 28 февраля 2026 (v2 — исправлен journal_id в role_permissions)
-- ═══════════════════════════════════════════════════════════════

BEGIN;

-- ─── 1. Сдвигаем display_order ───
UPDATE journal_columns
SET display_order = display_order + 3
WHERE journal_id = 1
  AND display_order >= 29;

-- ─── 2. Добавляем столбцы ───
INSERT INTO journal_columns (journal_id, code, name, display_order, is_active)
VALUES
    (1, 'cutting_standard', 'Стандарт на нарезку', 29, true),
    (1, 'moisture_conditioning', 'Влагонасыщение', 30, true),
    (1, 'moisture_sample', 'Образец влагонасыщения (УКИ)', 31, true);

-- ─── 3. Назначаем права (копируем с manufacturing, добавляя journal_id = 1) ───

-- cutting_standard
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT rp.role,
       1,
       (SELECT id FROM journal_columns WHERE journal_id = 1 AND code = 'cutting_standard'),
       rp.access_level
FROM role_permissions rp
JOIN journal_columns jc ON rp.column_id = jc.id
WHERE jc.journal_id = 1 AND jc.code = 'manufacturing'
ON CONFLICT DO NOTHING;

-- moisture_conditioning
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT rp.role,
       1,
       (SELECT id FROM journal_columns WHERE journal_id = 1 AND code = 'moisture_conditioning'),
       rp.access_level
FROM role_permissions rp
JOIN journal_columns jc ON rp.column_id = jc.id
WHERE jc.journal_id = 1 AND jc.code = 'manufacturing'
ON CONFLICT DO NOTHING;

-- moisture_sample
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT rp.role,
       1,
       (SELECT id FROM journal_columns WHERE journal_id = 1 AND code = 'moisture_sample'),
       rp.access_level
FROM role_permissions rp
JOIN journal_columns jc ON rp.column_id = jc.id
WHERE jc.journal_id = 1 AND jc.code = 'manufacturing'
ON CONFLICT DO NOTHING;

COMMIT;

-- ═══════════════════════════════════════════════════════════════
-- ПРОВЕРКА:
--
-- SELECT code, name, display_order FROM journal_columns
-- WHERE journal_id = 1
-- AND code IN ('manufacturing', 'cutting_standard', 'moisture_conditioning',
--              'moisture_sample', 'uzk_required', 'further_movement')
-- ORDER BY display_order;
--
-- SELECT rp.role, jc.code, rp.access_level
-- FROM role_permissions rp
-- JOIN journal_columns jc ON rp.column_id = jc.id
-- WHERE jc.code IN ('moisture_conditioning', 'moisture_sample', 'cutting_standard')
-- ORDER BY jc.code, rp.role;
-- ═══════════════════════════════════════════════════════════════
