PROGRAM main
  VAR
    nivel_ma_x100 : INT AT %IW0;
    caudal_entrada : INT AT %IW1;
    caudal_salida : INT AT %IW2;
    confirmacion_marcha : INT AT %IW3;
    seta_pulsada : INT AT %IW4;
    velocidad_real_bomba_pct : INT AT %IW5;
    bomba_marcha : INT AT %QW0;
    bomba_velo : INT AT %QW1;
    valvula_abrir : INT AT %QW2;
    SP_ARRANQUE_BOMBA : REAL := 300.0;
    SP_RESERVA : REAL := 200.0;
    SP_REARME_CONSUMO : REAL := 250.0;
    SP_LLENO : REAL := 900.0;
    SP_ALARMA_ALTA : REAL := 950.0;
    SP_ALARMA_BAJA : REAL := 100.0;
    MA_MIN_VALIDO : INT := 350;
    MA_MAX_VALIDO : INT := 2050;
    VELOCIDAD_AUTO : INT := 75;
    nivel_litros : REAL;
    caudal_entrada_lpm : REAL;
    caudal_salida_lpm : REAL;
    fallo_sensor : BOOL;
    fallo_arranque : BOOL;
    alarma_nivel_alto : BOOL;
    alarma_nivel_bajo : BOOL;
    en_reserva : BOOL;
    bomba_auto_marcha : BOOL;
    consumo_permitido : BOOL;
    orden_marcha : BOOL;
    seguridades_ok : BOOL;
    seta_activa : BOOL;
    contactor_cerrado : BOOL;
    prev_modo : INT;
    modo_manual : INT AT %MW106;
    mando_manual_marcha : INT AT %MW107;
    mando_manual_valvula : INT AT %MW108;
    reset_fallos : INT AT %MW109;
    velocidad_manual_pct : INT AT %MW110;
    seta_scada : INT AT %MW111;
    hmi_nivel_x10 : INT AT %MW100;
    hmi_nivel_ma : INT AT %MW101;
    hmi_caudal_ent : INT AT %MW102;
    hmi_caudal_sal : INT AT %MW103;
    hmi_velocidad : INT AT %MW104;
    hmi_estado : INT AT %MW105;
    TON_ARRANQUE : TON;
    TON_PARO : TON;
  END_VAR

seta_activa := (seta_pulsada <> 0) OR (seta_scada <> 0);
contactor_cerrado := (confirmacion_marcha <> 0);

nivel_litros := (INT_TO_REAL(nivel_ma_x100) - 400.0) / 1600.0 * 1000.0;
caudal_entrada_lpm := (INT_TO_REAL(caudal_entrada) - 400.0) / 1600.0 * 150.0;
caudal_salida_lpm := (INT_TO_REAL(caudal_salida) - 400.0) / 1600.0 * 150.0;

fallo_sensor := (nivel_ma_x100 < MA_MIN_VALIDO) OR (nivel_ma_x100 > MA_MAX_VALIDO);
alarma_nivel_alto := (nivel_litros >= SP_ALARMA_ALTA) AND NOT fallo_sensor;
alarma_nivel_bajo := (nivel_litros <= SP_ALARMA_BAJA) AND NOT fallo_sensor;
seguridades_ok := NOT seta_activa AND NOT fallo_arranque AND NOT fallo_sensor;

IF nivel_litros <= SP_RESERVA THEN
    en_reserva := TRUE;
END_IF;
IF nivel_litros >= SP_REARME_CONSUMO THEN
    en_reserva := FALSE;
END_IF;
consumo_permitido := NOT en_reserva AND NOT fallo_sensor AND NOT seta_activa;

IF (nivel_litros <= SP_ARRANQUE_BOMBA) AND NOT fallo_sensor THEN
    bomba_auto_marcha := TRUE;
END_IF;
IF (nivel_litros >= SP_LLENO) OR fallo_sensor THEN
    bomba_auto_marcha := FALSE;
END_IF;

(* NUEVO: al pasar a MANUAL se conserva el estado de la bomba y se siembra consigna *)
IF (modo_manual <> 0) AND (prev_modo = 0) THEN
    IF bomba_auto_marcha THEN
        mando_manual_marcha := 1;
    ELSE
        mando_manual_marcha := 0;
    END_IF;
    velocidad_manual_pct := VELOCIDAD_AUTO;
END_IF;
prev_modo := modo_manual;

IF (modo_manual <> 0) THEN
    orden_marcha := (mando_manual_marcha <> 0);
ELSE
    orden_marcha := bomba_auto_marcha;
END_IF;
IF NOT seguridades_ok THEN
    orden_marcha := FALSE;
END_IF;

TON_ARRANQUE(IN := orden_marcha AND NOT contactor_cerrado, PT := T#3s);
TON_PARO(IN := NOT orden_marcha AND contactor_cerrado, PT := T#3s);
IF TON_ARRANQUE.Q OR TON_PARO.Q THEN
    fallo_arranque := TRUE;
END_IF;
IF (reset_fallos <> 0) AND NOT seta_activa THEN
    fallo_arranque := FALSE;
END_IF;
reset_fallos := 0;                       (* NUEVO: reset por pulso *)

IF orden_marcha THEN
    bomba_marcha := 1;
ELSE
    bomba_marcha := 0;
END_IF;

IF NOT orden_marcha THEN
    bomba_velo := 0;
ELSIF (modo_manual <> 0) THEN
    (* NUEVO: consigna por defecto y clamp *)
    IF velocidad_manual_pct <= 0 THEN
        bomba_velo := VELOCIDAD_AUTO;
    ELSIF velocidad_manual_pct > 100 THEN
        bomba_velo := 100;
    ELSE
        bomba_velo := velocidad_manual_pct;
    END_IF;
ELSE
    bomba_velo := VELOCIDAD_AUTO;
END_IF;

IF (modo_manual <> 0) THEN
    IF (mando_manual_valvula <> 0) AND NOT seta_activa THEN
        valvula_abrir := 1;
    ELSE
        valvula_abrir := 0;
    END_IF;
ELSIF consumo_permitido THEN
    valvula_abrir := 1;
ELSE
    valvula_abrir := 0;
END_IF;

IF nivel_litros < 0.0 THEN
    hmi_nivel_x10 := 0;
ELSE
    hmi_nivel_x10 := REAL_TO_INT(nivel_litros * 10.0);
END_IF;
hmi_nivel_ma := nivel_ma_x100;
IF caudal_entrada_lpm < 0.0 THEN
    hmi_caudal_ent := 0;
ELSE
    hmi_caudal_ent := REAL_TO_INT(caudal_entrada_lpm * 10.0);
END_IF;
IF caudal_salida_lpm < 0.0 THEN
    hmi_caudal_sal := 0;
ELSE
    hmi_caudal_sal := REAL_TO_INT(caudal_salida_lpm * 10.0);
END_IF;
hmi_velocidad := velocidad_real_bomba_pct;

hmi_estado := 0;
IF contactor_cerrado  THEN hmi_estado := hmi_estado + 1;   END_IF;
IF seta_activa        THEN hmi_estado := hmi_estado + 2;   END_IF;
IF fallo_sensor       THEN hmi_estado := hmi_estado + 4;   END_IF;
IF fallo_arranque     THEN hmi_estado := hmi_estado + 8;   END_IF;
IF alarma_nivel_alto  THEN hmi_estado := hmi_estado + 16;  END_IF;
IF alarma_nivel_bajo  THEN hmi_estado := hmi_estado + 32;  END_IF;
IF en_reserva         THEN hmi_estado := hmi_estado + 64;  END_IF;
IF (modo_manual <> 0) THEN hmi_estado := hmi_estado + 128; END_IF;
IF bomba_marcha <> 0  THEN hmi_estado := hmi_estado + 256; END_IF;
IF valvula_abrir <> 0 THEN hmi_estado := hmi_estado + 512; END_IF;

END_PROGRAM