-- ═══════════════════════════════════════════════════════════════════
-- МИГРАЦИЯ v3.29.0 (часть 2) — Поверки: расширение equipment_maintenance
-- ═══════════════════════════════════════════════════════════════════
--
-- Добавляет поля для хранения данных о поверках/аттестациях:
--   certificate_number — номер свидетельства
--   valid_until — дата окончания действия
--   verification_organization — организация-поверитель
--   verification_result — результат (SUITABLE/UNSUITABLE)
--   fgis_arshin_number — номер записи в ФГИС «Аршин»
--
-- Применение: pgAdmin → выполнить
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE equipment_maintenance
    ADD COLUMN IF NOT EXISTS certificate_number VARCHAR(200) DEFAULT '' NOT NULL,
    ADD COLUMN IF NOT EXISTS valid_until DATE,
    ADD COLUMN IF NOT EXISTS verification_organization VARCHAR(300) DEFAULT '' NOT NULL,
    ADD COLUMN IF NOT EXISTS verification_result VARCHAR(20) DEFAULT '' NOT NULL,
    ADD COLUMN IF NOT EXISTS fgis_arshin_number VARCHAR(100) DEFAULT '' NOT NULL;

COMMENT ON COLUMN equipment_maintenance.certificate_number IS 'Номер свидетельства о поверке/аттестации';
COMMENT ON COLUMN equipment_maintenance.valid_until IS 'Дата окончания действия свидетельства';
COMMENT ON COLUMN equipment_maintenance.verification_organization IS 'Организация-поверитель';
COMMENT ON COLUMN equipment_maintenance.verification_result IS 'Результат: SUITABLE (пригоден) / UNSUITABLE (непригоден)';
COMMENT ON COLUMN equipment_maintenance.fgis_arshin_number IS 'Номер записи в ФГИС «Аршин»';

COMMIT;
