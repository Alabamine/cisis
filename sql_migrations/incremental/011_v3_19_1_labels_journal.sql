-- ============================================================
-- 011_v3_19_1_labels_journal.sql
-- Вынос генератора этикеток в отдельный журнал LABELS
-- ============================================================

BEGIN;

-- 1. Создаём журнал
INSERT INTO journals (code, name) VALUES ('LABELS', 'Генератор этикеток');

-- 2. Создаём столбец access
INSERT INTO journal_columns (journal_id, code, name, display_order, is_active)
SELECT j.id, 'access', 'Доступ', 1, true
FROM journals j WHERE j.code = 'LABELS';

-- 3. Переносим права: labels_access (SAMPLES) → access (LABELS)
INSERT INTO role_permissions (role, journal_id, column_id, access_level)
SELECT rp.role,
       (SELECT id FROM journals WHERE code = 'LABELS'),
       (SELECT jc.id FROM journal_columns jc JOIN journals j ON j.id = jc.journal_id WHERE j.code = 'LABELS' AND jc.code = 'access'),
       rp.access_level
FROM role_permissions rp
JOIN journal_columns jc ON jc.id = rp.column_id
WHERE jc.code = 'labels_access';

-- 4. Удаляем старые права на labels_access
DELETE FROM role_permissions
WHERE column_id = (
    SELECT jc.id FROM journal_columns jc
    JOIN journals j ON j.id = jc.journal_id
    WHERE j.code = 'SAMPLES' AND jc.code = 'labels_access'
);

-- 5. Удаляем столбец labels_access из SAMPLES
DELETE FROM journal_columns
WHERE code = 'labels_access'
  AND journal_id = (SELECT id FROM journals WHERE code = 'SAMPLES');

COMMIT;
