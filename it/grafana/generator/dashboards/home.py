"""00 · Vision general: la portada. Responde en 5 segundos a "¿esta bien la planta?"."""
from lib import *  # noqa: F403

UID = "otb-home"

# Estado de planta derivado del bitmask con prioridad: seta (x1000) > fallos (x100) > contactor (x10)
PLANT_STATE_Q = (
    'SELECT (FLOOR(last("value") / 2) % 2) * 1000 '
    '+ (FLOOR(last("value") / 4) % 2 + FLOOR(last("value") / 8) % 2) * 100 '
    '+ (last("value") % 2) * 10 '
    f'FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter'
)
PLANT_STATE_MAP = range_map([
    (1000, None, "EMERGENCIA", EMERG),
    (100, 999, "FALLO", CRIT),
    (10, 99, "EN MARCHA", OK),
    (0, 9, "PARADA", INACTIVE),
])

ACTIVE_ALARMS_SQL = """SELECT
  count(*) AS "Activas",
  COALESCE(max(CASE severity WHEN 'CRITICAL' THEN 3 WHEN 'HIGH' THEN 2 ELSE 1 END), 0) AS "Máx."
FROM alarms
WHERE state <> 'RESOLVED'"""

ACTIVE_ALARM_TABLE_SQL = """SELECT
  severity::text AS "Severidad",
  variable AS "Variable",
  message AS "Mensaje",
  state::text AS "Estado",
  ts_active AS "Desde",
  EXTRACT(EPOCH FROM NOW() - ts_active) AS "Antigüedad"
FROM alarms
WHERE state <> 'RESOLVED'
ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END, ts_active
LIMIT 8"""

SEVERITY_RANK_MAP = value_map({0: ("—", NEUTRAL), 1: ("WARNING", YELLOW), 2: ("HIGH", WARN), 3: ("CRITICAL", CRIT)})


def _kpis() -> list[dict]:
    h = 4
    return [
        stat("Estado de planta", grid(0, 0, 3, h), [influx("A", PLANT_STATE_Q)],
             mappings=PLANT_STATE_MAP, links=[link("Ver proceso", "otb-process")],
             desc="Estado derivado del registro de estado con prioridad: seta de emergencia > fallo "
                  "(sensor o arranque) > contactor de bomba > parada.", value_size=22),
        stat("PLC", grid(3, 0, 3, h),
             [influx("A", f'SELECT last("online") FROM "plc_status" WHERE ({PLC_FILTER}) AND $timeFilter')],
             mappings=[value_map({1: ("EN LÍNEA", OK), 0: ("SIN CONEXIÓN", CRIT)})],
             links=[link("Ver sistema", "otb-system")], value_size=22, noValue="SIN DATOS",
             desc="Último heartbeat del gateway Modbus → MQTT."),
        stat("Disponibilidad", grid(6, 0, 3, h),
             [influx("A", f'SELECT mean("online") * 100.0 FROM "plc_status" WHERE ({PLC_FILTER}) AND $timeFilter')],
             unit=U_PERCENT, decimals=1, color_mode="value", graph="none",
             thresholds=steps((None, CRIT), (80, WARN), (95, PROCESS)),
             links=[link("Ver sistema", "otb-system")],
             desc="Porcentaje de heartbeats online en el rango. < 95 % aviso, < 80 % crítico."),
        stat("OEE", grid(9, 0, 3, h),
             [influx("A", f'SELECT mean("online") FROM "plc_status" WHERE ({PLC_FILTER}) AND $timeFilter',
                     "disponibilidad"),
              influx("B", f'SELECT mean("value"){FLOW} / {NOMINAL_FLOW_LPM} * 100.0 FROM "sensor_readings" '
                          f'WHERE ({where("caudal_sal")}) AND $timeFilter', "rendimiento")],
             transformations=[t_join(), t_binary("OEE", "disponibilidad", "*", "rendimiento", replace=True)],
             unit=U_PERCENT, decimals=1, color_mode="value",
             thresholds=steps((None, CRIT), (40, WARN), (60, PROCESS)),
             links=[link("Ver proceso", "otb-process")],
             desc=f"OEE = disponibilidad × rendimiento (caudal de salida / {NOMINAL_FLOW_LPM:g} l/min nominal). Calidad asumida 100 %."),
        stat("Producción", grid(12, 0, 3, h),
             [influx("A", f'SELECT integral("value"){FLOW} / 60.0 FROM "sensor_readings" '
                          f'WHERE ({where("caudal_sal")}) AND $timeFilter')],
             unit=U_LITRE, decimals=0, color_mode="value", thresholds=steps((None, PROCESS)),
             links=[link("Ver proceso", "otb-process")],
             desc="Volumen bombeado en el rango: integral del caudal de salida."),
        stat("Alarmas activas", grid(15, 0, 3, h), [sql(ACTIVE_ALARMS_SQL)],
             text_mode="value_and_name", color_mode="value", orientation="horizontal",
             overrides=[override("Activas", thresholds=steps((None, NEUTRAL), (1, WARN))),
                        override("Máx.", mappings=[SEVERITY_RANK_MAP])],
             links=[link("Ver alarmas", "otb-alarms")],
             desc="Alarmas no resueltas y la severidad máxima entre ellas."),
        gauge("Riesgo", grid(18, 0, 3, h),
              [api("A", "/api/maintenance/recommendations", "", [("score", "Riesgo", "number")])],
              unit=U_NONE, min_=0, max_=100, decimals=0,
              thresholds=steps((None, PROCESS), (30, WARN), (60, CRIT)),
              links=[link("Ver mantenimiento", "otb-maintenance")],
              desc="Score del endpoint de mantenimiento predictivo (F11). ≥ 30 MEDIO, ≥ 60 ALTO."),
        stat("Gemelo", grid(21, 0, 3, h),
             [influx("A", f'SELECT last("deviation") FROM "twin_state" WHERE ({PLC_FILTER}) AND $timeFilter')],
             unit=U_LITRE, decimals=1, color_mode="value",
             thresholds=steps((None, CRIT), (-20, WARN), (-10, PROCESS), (10, WARN), (20, CRIT)),
             links=[link("Ver gemelo", "otb-twin")], noValue="SIN DATOS",
             desc="Nivel real − nivel modelado por el gemelo. |desviación| > 20 L dispara alarma de balance."),
    ]


# --------------------------------------------------------------------------- sinoptico (Canvas)
def _el(kind: str, name: str, left: float, top: float, width: float, height: float, *, text: dict | None = None,
        size: int = 14, color: str = "#E0E0E0", bg: dict | None = None, border: str | None = None,
        radius: int = 0, connections: list | None = None) -> dict:
    """Elemento Canvas con posicionamiento escalable (porcentajes del panel)."""
    return {
        "type": kind, "name": name,
        "config": {"text": text or {"mode": "fixed", "fixed": ""}, "color": {"fixed": color}, "size": size,
                   "align": "center", "valign": "middle"},
        "background": bg or {"color": {"fixed": TRANSPARENT}},
        "border": {"color": {"fixed": border or TRANSPARENT}, "width": 2 if border else 0, "radius": radius},
        "constraint": {"horizontal": "scale", "vertical": "scale"},
        "placement": {"left": left, "top": top, "right": 100 - left - width, "bottom": 100 - top - height},
        "connections": connections or [],
    }


def _field(name: str) -> dict:
    return {"mode": "field", "field": name, "fixed": ""}


def _fixed(value: str) -> dict:
    return {"mode": "fixed", "fixed": value}


def _pipe(target: str, field: str) -> dict:
    return {"source": {"x": 1, "y": 0}, "target": {"x": -1, "y": 0}, "targetName": target, "path": "straight",
            "color": {"field": field, "fixed": INACTIVE}, "size": {"fixed": 2, "min": 1, "max": 10},
            "lineStyle": {"style": "dashed", "animate": True}}


def _synoptic() -> dict:
    # Flujo real (programa PLC): acometida -> P-101 (llenado) -> TK-101 -> V-101 (consumo) -> salida
    elements = [
        _el("text", "titulo", 2, 3, 60, 8, text=_fixed("BALSA TK-101 · LLENADO P-101 · CONSUMO V-101"), size=14,
            color=NEUTRAL),
        _el("text", "modo", 70, 3, 28, 8, text=_field("modo"), size=14),
        # Acometida
        _el("text", "lbl_ent", 1, 30, 16, 6, text=_fixed("ENTRADA"), size=11, color=NEUTRAL),
        _el("metric-value", "caudal_ent", 1, 36, 16, 10, text=_field("caudal_ent"), size=16,
            border="#3A3A3A", radius=6, connections=[_pipe("P-101", "caudal_ent")]),
        # Bomba de llenado
        _el("ellipse", "P-101", 21, 32, 10, 18, text=_fixed("P-101"), size=12, color="#0B1A0B",
            bg={"color": {"field": "bomba", "fixed": INACTIVE}}, border="#8E8E8E",
            connections=[_pipe("TK-101", "caudal_ent")]),
        _el("metric-value", "bomba_estado", 17, 53, 18, 7, text=_field("bomba"), size=12),
        _el("metric-value", "velocidad", 17, 60, 18, 7, text=_field("velocidad"), size=13),
        # Deposito
        _el("rectangle", "TK-101", 38, 14, 24, 58, text=_fixed(""), bg={"color": {"field": "nivel", "fixed": "#1E2A3A"}},
            border="#5A6B80", radius=10, connections=[_pipe("V-101", "caudal_sal")]),
        _el("text", "tk_tag", 38, 16, 24, 7, text=_fixed("TK-101"), size=12, color="#DDE6F0"),
        _el("metric-value", "nivel_val", 38, 33, 24, 16, text=_field("nivel"), size=30, color="#FFFFFF"),
        _el("metric-value", "sensor_val", 38, 55, 24, 8, text=_field("sensor_ma"), size=13, color="#DDE6F0"),
        # Valvula de consumo
        _el("rectangle", "V-101", 67, 36, 10, 10, text=_fixed("V-101"), size=11, color="#FFFFFF",
            bg={"color": {"field": "valvula", "fixed": INACTIVE}}, border="#8E8E8E", radius=4,
            connections=[_pipe("salida", "caudal_sal")]),
        _el("metric-value", "valvula_estado", 63, 53, 18, 7, text=_field("valvula"), size=12),
        # Consumo
        _el("text", "lbl_sal", 83, 30, 16, 6, text=_fixed("CONSUMO"), size=11, color=NEUTRAL),
        _el("metric-value", "salida", 83, 36, 16, 10, text=_field("caudal_sal"), size=16, border="#3A3A3A", radius=6),
        # Pie: consigna y estado de planta, con etiqueta
        _el("text", "lbl_consigna", 2, 77, 45, 5, text=_fixed("CONSIGNA MANUAL P-101"), size=10, color=NEUTRAL),
        _el("text", "lbl_estado", 53, 77, 45, 5, text=_fixed("ESTADO DE PLANTA"), size=10, color=NEUTRAL),
        _el("metric-value", "consigna", 2, 83, 45, 12, text=_field("consigna"), size=13, border="#3A3A3A", radius=6),
        _el("metric-value", "estado_planta", 53, 83, 45, 12, text=_field("estado_planta"), size=13,
            bg={"color": {"field": "estado_planta", "fixed": INACTIVE}}, radius=6),
    ]
    targets = [
        latest("A", "nivel_x10", "nivel", " / 10.0"),
        latest("B", "caudal_ent", "caudal_ent", FLOW),
        latest("C", "caudal_sal", "caudal_sal", FLOW),
        latest("D", "velocidad", "velocidad"),
        latest("E", "nivel_ma", "sensor_ma", " / 100.0"),
        latest("F", "modo_manual", "modo"),
        # Estado real de V-101: bit 512 (orden_apertura_valvula); mando_valvula solo actua en MANUAL
        influx("G", f'SELECT FLOOR(last("value") / 512) % 2 FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter', "valvula"),
        latest("H", "consigna_manual", "consigna"),
        influx("I", f'SELECT last("value") % 2 FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter', "bomba"),
        influx("J", PLANT_STATE_Q, "estado_planta"),
    ]
    flow_thr = steps((None, INACTIVE), (1, PROCESS))
    # Sin displayName: los elementos del Canvas localizan cada campo por su alias
    overrides = [
        override("nivel", unit=U_LITRE, decimals=0,
                 thresholds=steps((None, "#6B2A2A"), (100, "#1F3B5C"), (900, "#6B4A1F"))),
        override("caudal_ent", unit=U_FLOW, decimals=1, thresholds=flow_thr),
        override("caudal_sal", unit=U_FLOW, decimals=1, thresholds=flow_thr),
        override("velocidad", unit=U_PERCENT, decimals=0),
        override("sensor_ma", unit=U_MA, decimals=2),
        override("modo", mappings=[value_map({0: ("MODO AUTOMÁTICO", NEUTRAL), 1: ("MODO MANUAL", WARN)})]),
        override("valvula", mappings=[value_map({0: ("CERRADA", INACTIVE), 1: ("ABIERTA", "#1F4E79")})]),
        override("consigna", unit=U_PERCENT, decimals=0),
        override("bomba", mappings=[value_map({0: ("PARADA", INACTIVE), 1: ("EN MARCHA", OK)})]),
        override("estado_planta", mappings=PLANT_STATE_MAP),
    ]
    panel = {
        "id": next_id(), "type": "canvas", "title": "Sinóptico de planta",
        "description": "Vista viva del proceso: color del depósito según banda de nivel (bajo < 100 L, alto > 900 L), "
                       "bomba de llenado P-101 verde en marcha, válvula de consumo V-101 azul abierta, tuberías animadas "
                "cuando hay caudal.",
        "gridPos": grid(0, 4, 12, 13), "datasource": INFLUX, "targets": targets,
        "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": steps((None, NEUTRAL)),
                                     "mappings": []}, "overrides": overrides},
        "options": {"inlineEditing": False, "showAdvancedTypes": True, "panZoom": False, "infinitePan": False,
                    "root": {"type": "frame", "name": "root", "elements": elements,
                             "background": {"color": {"fixed": TRANSPARENT}},
                             "border": {"color": {"fixed": TRANSPARENT}},
                             "constraint": {"horizontal": "left", "vertical": "top"},
                             "placement": {"left": 0, "top": 0, "width": 100, "height": 100}}},
    }
    return panel


def build() -> dict:
    reset_ids()
    panels = _kpis()
    panels.append(_synoptic())
    panels += [
        timeseries("Nivel real vs gemelo digital", grid(12, 4, 12, 7),
                   [series("A", "nivel_x10", "Nivel real", " / 10.0"),
                    influx("B", f'SELECT mean("level_model") FROM "twin_state" WHERE ({PLC_FILTER}) AND $timeFilter '
                                "GROUP BY time($__interval) fill(none)", "Modelo gemelo")],
                   unit=U_LITRE, decimals=1, legend_calcs=["lastNotNull"],
                   overrides=[override("Nivel real", color=fixed(PROCESS)),
                              override("Modelo gemelo", color=fixed(MODEL), custom__fillOpacity=0,
                                       custom__lineStyle={"fill": "dash", "dash": [8, 6]})],
                   desc="Nivel medido frente al nivel que predice el gemelo por balance de masas. "
                        "Si se separan más de 20 L, hay pérdida o aporte no medido."),
        timeseries("Caudales", grid(12, 11, 12, 6),
                   [series("A", "caudal_ent", "Entrada", FLOW), series("B", "caudal_sal", "Salida", FLOW)],
                   unit=U_FLOW, decimals=1,
                   overrides=[override("Entrada", color=fixed(PROCESS)), override("Salida", color=fixed("#4FC3C3"))],
                   desc="Caudal de entrada y de salida del depósito."),
        table("Alarmas activas", grid(0, 17, 16, 7), [sql(ACTIVE_ALARM_TABLE_SQL)], no_value="Sin alarmas activas",
              desc="Alarmas no resueltas, ordenadas por severidad y antigüedad.",
              overrides=[
                  override("Severidad", custom__width=110, custom__cellOptions={"type": "color-background", "mode": "basic"},
                           mappings=[value_map({k: (k, v) for k, v in SEVERITY_COLORS.items()})]),
                  override("Estado", custom__width=130, custom__cellOptions={"type": "color-text"},
                           mappings=[value_map({k: (k, v) for k, v in STATE_COLORS.items()})]),
                  override("Variable", custom__width=110),
                  override("Desde", unit="time:DD/MM HH:mm:ss", custom__width=140),
                  override("Antigüedad", unit="dtdurations", custom__width=150),
              ], links=[]),
        stat("Último dato recibido", grid(16, 17, 8, 3), [latest("A", "nivel_x10", "nivel")],
             unit=U_FROM_NOW, fields="/^Time$/", color_mode="none", thresholds=steps((None, PROCESS)),
             desc="Antigüedad de la última lectura almacenada en el historian.", value_size=24),
        state_timeline("Conectividad PLC", grid(16, 20, 8, 4),
                       [influx("A", f'SELECT last("online") FROM "plc_status" WHERE ({PLC_FILTER}) AND $timeFilter '
                                    "GROUP BY time($__interval) fill(previous)", "PLC")],
                       mappings=[value_map({1: ("En línea", OK), 0: ("Sin conexión", CRIT)})],
                       desc="Historial de conexión del PLC en el rango seleccionado."),
    ]
    return dashboard(UID, "00 · Visión general", panels, refresh="5s", time_from="now-1h",
                     description="Portada de la planta: estado, KPIs, sinóptico y alarmas activas.")
