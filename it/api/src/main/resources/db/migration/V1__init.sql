-- OT-Bridge: esquema inicial de la API (Flyway V1)
-- PostgreSQL 16

CREATE TYPE alarm_severity AS ENUM ('WARNING', 'HIGH', 'CRITICAL');
CREATE TYPE alarm_state AS ENUM ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED');

CREATE TABLE machines (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(64)  NOT NULL UNIQUE,
    description  VARCHAR(255),
    online       BOOLEAN      NOT NULL DEFAULT FALSE,
    last_seen_ts TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE sensors (
    id          BIGSERIAL PRIMARY KEY,
    machine_id  BIGINT        NOT NULL REFERENCES machines (id),
    variable    VARCHAR(64)   NOT NULL,
    unit        VARCHAR(32),
    description VARCHAR(255),
    last_value  DOUBLE PRECISION,
    last_ts     TIMESTAMPTZ,
    UNIQUE (machine_id, variable)
);
CREATE INDEX idx_sensors_machine ON sensors (machine_id);

CREATE TABLE alarms (
    id          BIGSERIAL PRIMARY KEY,
    machine_id  BIGINT         NOT NULL REFERENCES machines (id),
    variable    VARCHAR(64)    NOT NULL,
    severity    alarm_severity NOT NULL,
    state       alarm_state    NOT NULL DEFAULT 'ACTIVE',
    message     VARCHAR(255),
    ts_active   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    ts_ack      TIMESTAMPTZ,
    ts_resolved TIMESTAMPTZ,
    ack_by      VARCHAR(64),
    version     BIGINT         NOT NULL DEFAULT 0
);
CREATE INDEX idx_alarms_state ON alarms (state);
CREATE INDEX idx_alarms_machine_state ON alarms (machine_id, state);
CREATE INDEX idx_alarms_dedupe ON alarms (variable, severity, state, ts_active);

CREATE TABLE thresholds (
    id       BIGSERIAL PRIMARY KEY,
    variable VARCHAR(64)    NOT NULL,
    operator VARCHAR(4)     NOT NULL,
    value    DOUBLE PRECISION NOT NULL,
    severity alarm_severity NOT NULL,
    message  VARCHAR(255),
    enabled  BOOLEAN        NOT NULL DEFAULT TRUE
);

-- Semilla: maquina plc01 y sus 6 sensores (contrato MQTT, AGENTS.md seccion 6)
INSERT INTO machines (name, description) VALUES ('plc01', 'Planta simulada - deposito');

INSERT INTO sensors (machine_id, variable, unit, description) VALUES
    (1, 'nivel_x10',  'Lx10',   'Nivel del deposito x10'),
    (1, 'nivel_ma',   'mA x100','Senal cruda del sensor de nivel'),
    (1, 'caudal_ent', 'lpm',    'Caudal de entrada'),
    (1, 'caudal_sal', 'lpm',    'Caudal de salida'),
    (1, 'velocidad',  '%',      'Velocidad de la bomba'),
    (1, 'estado',     '',       'Bitmask de estado');

-- Semilla: umbrales iniciales (reglas base de la Fase 6)
INSERT INTO thresholds (variable, operator, value, severity, message, enabled) VALUES
    ('nivel_x10', 'lt',  1000, 'WARNING',  'Nivel bajo',          TRUE),
    ('nivel_x10', 'gt',  9000, 'HIGH',     'Nivel alto',          TRUE),
    ('estado',    'bit', 4,    'CRITICAL', 'Fallo sensor',        TRUE),
    ('estado',    'bit', 8,    'CRITICAL', 'Fallo de arranque',   TRUE),
    ('estado',    'bit', 2,    'CRITICAL', 'Seta de emergencia',  TRUE);
