-- V3: sensores de mando (registros de escritura del PLC, observados en IT como solo lectura)
INSERT INTO sensors (machine_id, variable, unit, description) VALUES
    (1, 'modo_manual',     '',   'Modo de operacion (0 = auto, 1 = manual)'),
    (1, 'mando_marcha',    '',   'Mando manual de marcha de bomba'),
    (1, 'mando_valvula',   '',   'Mando manual de apertura de valvula'),
    (1, 'reset_fallos',    '',   'Reset de fallos (flanco)'),
    (1, 'consigna_manual', '%',  'Consigna manual de velocidad de bomba');
