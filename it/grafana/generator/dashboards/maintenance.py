"""04 · Mantenimiento predictivo: score de la API (F11), indicadores y desgaste derivado del historico."""
from lib import *  # noqa: F403

UID = "otb-maintenance"

RISK_COLORS = {"BAJO": "#1F3B5C", "MEDIO": WARN, "ALTO": CRIT}
RECOMMENDATION = {"BAJO": ("Operación normal", "#1F3B5C"),
                  "MEDIO": ("Planificar inspección", WARN),
                  "ALTO": ("Intervención prioritaria", CRIT)}

CONTACTOR = f'SELECT "value" % 2 AS b FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter'
# (|d| + d) / 2 vale 1 solo en un flanco 0->1: la suma cuenta arranques y devuelve 0 si no hay ninguno
STARTS = f'SELECT (abs("d") + "d") / 2 AS "s" FROM (SELECT difference("b") AS "d" FROM ({CONTACTOR}))'


def trend(title: str, x: int, targets: list, *, unit: str, thr: dict, style: str, desc: str,
          transformations: list | None = None, min_=None, max_=None, decimals: int = 1) -> dict:
    return timeseries(title, grid(x, 9, 6, 7), targets, unit=unit, thresholds=thr, threshold_style=style,
                      legend_calcs=["mean", "lastNotNull"], transformations=transformations, min_=min_, max_=max_,
                      decimals=decimals, color=fixed(PROCESS), desc=desc)


def five_min(ref: str, variable: str, alias: str, scale: str = "") -> dict:
    return series(ref, variable, alias, scale, interval="5m")


def build() -> dict:
    reset_ids()
    risk_api = api("A", "/api/maintenance/recommendations", "",
                   [("score", "Score", "number"), ("riskLevel", "Nivel", "string")])
    p = [
        gauge("Score de riesgo", grid(0, 0, 6, 9), [risk_api], unit=U_NONE, min_=0, max_=100, decimals=0,
              thresholds=steps((None, PROCESS), (30, WARN), (60, CRIT)),
              overrides=[override("Nivel", custom__hideFrom={"viz": True, "legend": True, "tooltip": True})],
              desc="Score heurístico del endpoint /api/maintenance/recommendations (última hora): "
                   "disponibilidad < 95 % +40, velocidad < 40 % +30, |balance| > 30 +30, sensor fuera de rango +30. "
                   "≥ 30 MEDIO, ≥ 60 ALTO."),
        stat("Nivel de riesgo", grid(6, 0, 4, 4), [risk_api], fields="/^Nivel$/", value_size=26,
             mappings=[value_map({k: (k, v) for k, v in RISK_COLORS.items()})],
             desc="Clasificación del riesgo calculada por la API."),
        stat("Recomendación", grid(6, 4, 4, 5), [risk_api], fields="/^Nivel$/", value_size=16,
             mappings=[value_map(RECOMMENDATION)],
             desc="Acción sugerida según el nivel de riesgo."),
        table("Indicadores de salud (última hora)", grid(10, 0, 14, 9),
              [api("A", "/api/maintenance/recommendations", "indicators",
                   [("name", "Indicador", "string"), ("value", "Valor", "number"), ("status", "Estado", "string")])],
              desc="Indicadores con los que la API calcula el score. Cualquier estado distinto de OK suma riesgo.",
              overrides=[override("Valor", decimals=1, custom__width=110),
                         override("Estado", custom__width=160, custom__cellOptions={"type": "color-background",
                                                                                    "mode": "basic"},
                                  mappings=[value_map({"OK": ("OK", "#1F3B5C")}),
                                            {"type": "regex", "options": {"pattern": "^(?!OK$).+$",
                                                                          "result": {"color": WARN, "index": 1}}}])]),

    ]
    p += [
        trend("Disponibilidad PLC", 0,
              [influx("A", f'SELECT mean("online") * 100.0 FROM "plc_status" WHERE ({PLC_FILTER}) AND $timeFilter '
                           "GROUP BY time(5m) fill(none)", "Disponibilidad")],
              unit=U_PERCENT, min_=0, max_=100, thr=steps((None, WARN), (95, TRANSPARENT)), style="line+area",
              desc="Media de heartbeats online cada 5 min. Por debajo del 95 % suma +40 al score."),
        trend("Velocidad media de bomba", 6, [five_min("A", "velocidad", "Velocidad")],
              unit=U_PERCENT, min_=0, max_=100, thr=steps((None, WARN), (40, TRANSPARENT)), style="line+area",
              desc="Velocidad media cada 5 min. Por debajo del 40 % suma +30 (posible degradación o paradas)."),
        trend("Pérdida no medida (gemelo)", 12,
              [influx("A", f'SELECT mean("leak_lpm") FROM "twin_state" WHERE ({PLC_FILTER}) AND $timeFilter '
                           "GROUP BY time(5m) fill(none)", "Pérdida")],
              unit=U_FLOW, decimals=1, thr=steps((None, WARN), (-3, TRANSPARENT), (3, WARN)), style="line+area",
              desc="Caudal no contabilizado estimado por el gemelo digital (media 5 min). |pérdida| > 3 l/min suma +30."),
        trend("Sensor de nivel", 18, [five_min("A", "nivel_ma", "Señal", " / 100.0")],
              unit=U_MA, min_=0, max_=24, decimals=2,
              thr=steps((None, CRIT), (3.5, TRANSPARENT), (20.5, CRIT)), style="line+area",
              desc="Señal media del transmisor. Fuera de 3,5–20,5 mA suma +30 (sensor degradado)."),

        stat("Horas de marcha", grid(0, 16, 6, 4),
             [influx("A", f'SELECT integral("b") / 3600.0 FROM ({CONTACTOR})')],
             unit=U_HOURS, decimals=2, color_mode="value", thresholds=steps((None, PROCESS)),
             desc="Tiempo con el contactor de bomba cerrado en el rango (integral del bit 1)."),
        stat("Arranques", grid(6, 16, 6, 4),
             [influx("A", f'SELECT sum("s") FROM ({STARTS})')],
             decimals=0, color_mode="value", thresholds=steps((None, PROCESS), (50, WARN), (100, CRIT)),
             noValue="0", desc="Número de arranques de bomba (flancos 0→1 del contactor). Muchos arranques = desgaste."),
        stat("Tiempo en fallo", grid(12, 16, 6, 4),
             [influx("A", 'SELECT integral("f") / 60.0 FROM (SELECT FLOOR("value" / 4) % 2 + FLOOR("value" / 8) % 2 '
                          f'AS "f" FROM "sensor_readings" WHERE ({where("estado")}) AND $timeFilter)')],
             unit="m", decimals=1, color_mode="value", thresholds=steps((None, PROCESS), (1, WARN), (15, CRIT)),
             desc="Minutos con fallo de sensor o de arranque activo."),
        stat("Utilización de bomba", grid(18, 16, 6, 4),
             [influx("A", f'SELECT mean("b") * 100.0 FROM ({CONTACTOR})')],
             unit=U_PERCENT, decimals=1, color_mode="value", thresholds=steps((None, PROCESS), (90, WARN)),
             desc="Porcentaje del rango con la bomba en marcha. > 90 % sostenido reduce margen de mantenimiento."),
        timeseries("Arranques por hora", grid(0, 20, 24, 7),
                   [influx("A", f'SELECT sum("s") FROM ({STARTS}) WHERE $timeFilter GROUP BY time(1h) fill(0)', "Arranques")],
                   decimals=0, legend_calcs=["sum", "max"],
                   custom={"drawStyle": "bars", "fillOpacity": 70, "lineWidth": 0, "gradientMode": "none"},
                   thresholds=steps((None, TRANSPARENT), (6, WARN)), threshold_style="dashed",
                   overrides=[override("Arranques", color=fixed(PROCESS))],
                   desc="Arranques de bomba por hora. Línea discontinua: 6 arranques/h, límite típico de motores."),
        table("Alarmas relacionadas con mantenimiento", grid(0, 27, 24, 7),
              [sql("""SELECT ts_active AS "Activada", variable AS "Variable", severity::text AS "Severidad",
  state::text AS "Estado", message AS "Mensaje",
  EXTRACT(EPOCH FROM COALESCE(ts_resolved, NOW()) - ts_active) AS "Duración"
FROM alarms
WHERE variable IN ('estado', 'velocidad', 'nivel_x10', 'balance') AND ts_active > NOW() - INTERVAL '7 days'
ORDER BY ts_active DESC LIMIT 50""")],
              desc="Alarmas de los últimos 7 días sobre las variables que alimentan el score.",
              overrides=[override("Activada", unit="time:DD/MM HH:mm", custom__width=120),
                         override("Severidad", custom__width=110,
                                  custom__cellOptions={"type": "color-background", "mode": "basic"},
                                  mappings=[value_map({k: (k, v) for k, v in SEVERITY_COLORS.items()})]),
                         override("Estado", custom__width=130, custom__cellOptions={"type": "color-text"},
                                  mappings=[value_map({k: (k, v) for k, v in STATE_COLORS.items()})]),
                         override("Duración", unit="dtdurations", custom__width=140)]),
    ]
    return dashboard(UID, "04 · Mantenimiento predictivo", p, refresh="1m", time_from="now-24h",
                     description="Score de riesgo, indicadores de salud, tendencias y desgaste de la bomba.")
