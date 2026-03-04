-- ============================================================================
-- CISIS v3.23.0 — Таблицы планового ТО оборудования
-- Файл: sql_migrations/incremental/017_v3_23_0_maintenance_plans.sql
-- Дата: 4 марта 2026
-- ============================================================================


-- ════════════════════════════════════════════════════════════════
-- 1. Таблица equipment_maintenance_plans (план/описание ТО)
-- ════════════════════════════════════════════════════════════════
-- Каждая запись — один вид ТО для конкретного оборудования.
--
-- Периодичность задаётся тремя полями:
--   frequency_count        — сколько раз за период (1, 2, 3...)
--   frequency_unit         — единица периода (DAY, WEEK, MONTH, YEAR)
--   frequency_period_value — за сколько единиц считается период
--
-- Примеры:
--   «1 раз в неделю»       → count=1, unit=WEEK,  period_value=1
--   «1 раз в месяц»        → count=1, unit=MONTH, period_value=1
--   «1 раз в 3 месяца»     → count=1, unit=MONTH, period_value=3
--   «1 раз в год»          → count=1, unit=YEAR,  period_value=1
--   «1 раз в 5 лет»        → count=1, unit=YEAR,  period_value=5
--   «2 раза в год»         → count=2, unit=YEAR,  period_value=1
--   «1 раз в 2 недели»     → count=1, unit=WEEK,  period_value=2
--   «по мере загрязнения»  → count=NULL, unit=NULL, period_value=NULL,
--                             condition='по мере загрязнения', is_condition_based=TRUE
--   «при необходимости,
--    но не реже 1 раз
--    в 5 лет»              → count=1, unit=YEAR, period_value=5,
--                             condition='при необходимости', is_condition_based=FALSE

CREATE TABLE IF NOT EXISTS equipment_maintenance_plans (
    id                      SERIAL PRIMARY KEY,

    -- Связь с оборудованием
    equipment_id            INTEGER      NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,


    -- Название / описание вида ТО
    name                    VARCHAR(300) NOT NULL,

    -- ── Периодичность: календарная часть ──
    frequency_count         INTEGER,                -- сколько раз за период (1, 2 ...)
    frequency_unit          VARCHAR(10)             -- единица периода
                            CHECK (frequency_unit IN ('DAY', 'WEEK', 'MONTH', 'YEAR')),
    frequency_period_value  INTEGER,                -- за сколько единиц (3 месяца, 5 лет...)

    -- ── Периодичность: условие ──
    frequency_condition     TEXT    DEFAULT '',      -- текстовое описание условия
    is_condition_based      BOOLEAN DEFAULT FALSE NOT NULL, -- TRUE = ТО по условию

    -- Дополнительно
    next_due_date           DATE,                   -- плановая дата следующего ТО
    is_active               BOOLEAN   DEFAULT TRUE NOT NULL,
    notes                   TEXT      DEFAULT '',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Если календарное ТО — все три поля периодичности обязательны
    CONSTRAINT chk_calendar_frequency CHECK (
        is_condition_based = TRUE
        OR (frequency_count IS NOT NULL
            AND frequency_unit IS NOT NULL
            AND frequency_period_value IS NOT NULL)
    )
);

COMMENT ON TABLE  equipment_maintenance_plans IS 'Планы (виды) регулярного ТО оборудования';
COMMENT ON COLUMN equipment_maintenance_plans.frequency_count IS 'Сколько раз за период (1 = один раз)';
COMMENT ON COLUMN equipment_maintenance_plans.frequency_unit IS 'Единица периода: DAY, WEEK, MONTH, YEAR';
COMMENT ON COLUMN equipment_maintenance_plans.frequency_period_value IS 'За сколько единиц считается период (3 = раз в 3 месяца, 5 = раз в 5 лет)';
COMMENT ON COLUMN equipment_maintenance_plans.frequency_condition IS 'Текстовое условие (при загрязнении, при поломке и т.д.)';
COMMENT ON COLUMN equipment_maintenance_plans.is_condition_based IS 'TRUE = ТО по условию, FALSE = по календарю';
COMMENT ON COLUMN equipment_maintenance_plans.next_due_date IS 'Расчётная дата следующего ТО (обновляется после выполнения)';

-- Индексы
CREATE INDEX IF NOT EXISTS idx_maint_plan_equipment
    ON equipment_maintenance_plans (equipment_id);

CREATE INDEX IF NOT EXISTS idx_maint_plan_next_due
    ON equipment_maintenance_plans (next_due_date)
    WHERE is_active = TRUE;



-- ════════════════════════════════════════════════════════════════
-- 2. Таблица equipment_maintenance_logs (журнал выполнения ТО)
-- ════════════════════════════════════════════════════════════════
-- Каждая запись — один факт выполнения конкретного ТО.
-- У одного плана может быть много записей в журнале.

CREATE TABLE IF NOT EXISTS equipment_maintenance_logs (
    id                  SERIAL PRIMARY KEY,

    -- Связь с планом ТО
    plan_id             INTEGER      NOT NULL REFERENCES equipment_maintenance_plans(id) ON DELETE CASCADE,

    -- Когда выполнено
    performed_date      DATE         NOT NULL,

    -- Кто выполнил
    performed_by_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,

    -- Кто проверил
    verified_by_id      INTEGER      REFERENCES users(id) ON DELETE SET NULL,

    -- Статус выполнения
    status              VARCHAR(20)  DEFAULT 'COMPLETED' NOT NULL
                        CHECK (status IN (
                            'COMPLETED',
                            'SKIPPED',
                            'PARTIAL',
                            'OVERDUE'
                        )),

    -- Дата проверки
    verified_date       DATE,

    -- Комментарий / результат
    notes               TEXT         DEFAULT '',
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP


);

COMMENT ON TABLE  equipment_maintenance_logs IS 'Журнал выполнения планового ТО оборудования';
COMMENT ON COLUMN equipment_maintenance_logs.plan_id IS 'Ссылка на вид ТО из equipment_maintenance_plans';
COMMENT ON COLUMN equipment_maintenance_logs.status IS 'COMPLETED, SKIPPED, PARTIAL, OVERDUE';

-- Индексы
CREATE INDEX IF NOT EXISTS idx_maint_log_plan
    ON equipment_maintenance_logs (plan_id);

CREATE INDEX IF NOT EXISTS idx_maint_log_date
    ON equipment_maintenance_logs (performed_date);

CREATE INDEX IF NOT EXISTS idx_maint_log_performed_by
    ON equipment_maintenance_logs (performed_by_id);

CREATE INDEX IF NOT EXISTS idx_maint_log_status
    ON equipment_maintenance_logs (status);


