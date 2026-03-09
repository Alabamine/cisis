-- ═══════════════════════════════════════════════════════════════
-- 025_v3_31_0_file_type_defaults_equipment.sql
-- Подпапки на диске для файлов оборудования
-- ═══════════════════════════════════════════════════════════════

INSERT INTO file_type_defaults (category, file_type, default_visibility, default_subfolder)
VALUES
    ('EQUIPMENT', 'VERIFICATION_CERT', 'ALL', 'verification_cert'),
    ('EQUIPMENT', 'ATTESTATION_CERT',  'ALL', 'attestation_cert'),
    ('EQUIPMENT', 'REPAIR_ACT',        'ALL', 'repair_act'),
    ('EQUIPMENT', 'MANUAL',            'ALL', 'manual'),
    ('EQUIPMENT', 'PASSPORT',          'ALL', 'passport'),
    ('EQUIPMENT', 'CERTIFICATE',       'ALL', 'certificate'),
    ('EQUIPMENT', 'OTHER',             'ALL', '')
ON CONFLICT (category, file_type) DO UPDATE
    SET default_subfolder = EXCLUDED.default_subfolder;

-- Результат: файлы оборудования будут ложиться в структуру:
-- MEDIA_ROOT/equipment/<eq_name>/verification_cert/файл.pdf
-- MEDIA_ROOT/equipment/<eq_name>/attestation_cert/файл.pdf
-- MEDIA_ROOT/equipment/<eq_name>/repair_act/файл.pdf
-- MEDIA_ROOT/equipment/<eq_name>/manual/файл.pdf
-- MEDIA_ROOT/equipment/<eq_name>/passport/файл.pdf
-- MEDIA_ROOT/equipment/<eq_name>/файл.pdf  (для OTHER — без подпапки)
