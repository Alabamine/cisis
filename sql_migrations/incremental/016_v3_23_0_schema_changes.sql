-- ============================================================================
-- CISIS v3.23.0 — Структурные изменения БД
-- Файл: sql_migrations/incremental/016_v3_23_0_schema_changes.sql
-- Дата: 3 марта 2026
-- Зависимость: 015_v3_22_0_parameters.sql
-- ============================================================================

-- ============================================================================
-- 1. Расширение столбца code в standards (VARCHAR(50) -> VARCHAR(100))
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'standards'
          AND column_name = 'code'
          AND character_maximum_length < 100
    ) THEN
        ALTER TABLE standards ALTER COLUMN code TYPE VARCHAR(100);
    END IF;
END $$;

COMMIT;