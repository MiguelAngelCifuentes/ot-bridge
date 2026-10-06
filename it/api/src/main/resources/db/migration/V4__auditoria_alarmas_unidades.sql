-- V4 (auditoria 2026-09-30): alarmas alineadas con el PLC, histeresis/retardo, identidad de alarma y unidades.

-- 1. Umbrales: el PLC ya calcula las alarmas de nivel (bits 16/32 de hmi_estado, 950 / 100 L); IT las
--    toma de ahi en vez de duplicar cifras. Se retiran las reglas molestas y las de demostracion:
--    "Nivel alto" (saltaba en cada llenado normal: 900 L es la parada normal), "Velocidad alta"
--    (saltaba con la consigna manual legitima del 100 %), "Demo KPI" y "Demo persistencia".
DELETE FROM thresholds WHERE variable IN ('nivel_x10', 'velocidad');
INSERT INTO thresholds (variable, operator, value, severity, message, enabled) VALUES
    ('estado', 'BIT', 16, 'HIGH', 'Nivel muy alto (>= 950 L)', TRUE),
    ('estado', 'BIT', 32, 'HIGH', 'Nivel muy bajo (<= 100 L)', TRUE);
UPDATE thresholds SET message = 'Fallo sensor de nivel' WHERE variable = 'estado' AND value = 4;
UPDATE thresholds SET message = 'Fallo de arranque P-101' WHERE variable = 'estado' AND value = 8;

-- 2. Histeresis y retardo por regla (ISA-18.2: evita el chattering medido en Grafana, ~21 %)
ALTER TABLE thresholds
    ADD COLUMN deadband      DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN delay_seconds INTEGER          NOT NULL DEFAULT 0;
UPDATE thresholds SET delay_seconds = 1 WHERE variable = 'estado' AND value = 8;
UPDATE thresholds SET delay_seconds = 2 WHERE variable = 'estado' AND value IN (16, 32);

-- 3. Identidad de alarma: antes (maquina, variable, severidad); los bits CRITICAL de 'estado' colapsaban
--    en una sola alarma. Ahora cada regla publica su propio codigo.
ALTER TABLE alarms ADD COLUMN code VARCHAR(64);
UPDATE alarms SET code = variable || ':' || lower(severity::text) WHERE code IS NULL;
ALTER TABLE alarms ALTER COLUMN code SET NOT NULL;
CREATE INDEX idx_alarms_machine_code_state ON alarms (machine_id, code, state);

-- 4. Sensores: unidades del contrato MQTT (valores enteros crudos del PLC) y variable seta_scada (MW111)
UPDATE sensors SET unit = 'L_x10'   WHERE variable = 'nivel_x10';
UPDATE sensors SET unit = 'mA_x100' WHERE variable = 'nivel_ma';
UPDATE sensors SET unit = 'lpm_x10', description = description || ' (l/min x10)'
    WHERE variable IN ('caudal_ent', 'caudal_sal');
UPDATE sensors SET unit = 'bitmask' WHERE variable = 'estado';
INSERT INTO sensors (machine_id, variable, unit, description)
SELECT id, 'seta_scada', '', 'Paro de emergencia SCADA (MW111)' FROM machines WHERE name = 'plc01'
ON CONFLICT (machine_id, variable) DO NOTHING;
