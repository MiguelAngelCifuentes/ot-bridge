"""03 · Gemelo digital: modelo de balance de masas frente a la planta real."""
from lib import *  # noqa: F403

UID = "otb-twin"
THRESHOLD_L = 20      # UMBRAL_L del servicio digital-twin
FLOW_DIVISOR = 10     # FLOW_DIVISOR del servicio digital-twin: caudales del contrato en l/min x10

TWIN = f'"twin_state" WHERE ({PLC_FILTER}) AND $timeFilter'


def twin_series(ref: str, expr: str, alias: str) -> dict:
    return influx(ref, f"SELECT {expr} FROM {TWIN} GROUP BY time($__interval) fill(none)", alias)


PARAMS = f"""
**Modelo** — observador de balance de masas (Luenberger), 1 Hz:

`nivel_modelo += (caudal_ent − caudal_sal) / {FLOW_DIVISOR} × dt / 60` &nbsp;·&nbsp; `nivel_modelo += k × (nivel_real − nivel_modelo) × dt`

**Parámetros:** umbral `{THRESHOLD_L} L` (histéresis de resolución al 50 %) · ganancia `k = 0,005 s⁻¹` · caudales del contrato en l/min ×{FLOW_DIVISOR} (`hmi_caudal_*` del PLC) · resincronización si pasan > 120 s sin lectura.
**Interpretación:** una pérdida no medida sostenida de *Q* unidades de caudal (l/min) produce una desviación estable ≈ *Q* / (60 k); el gemelo la estima como *pérdida no medida* y dispara la alarma de `balance` al superar el umbral.
"""


def build() -> dict:
    reset_ids()
    p = [
        stat("Estado del gemelo", grid(0, 0, 4, 4),
             [influx("A", f'SELECT last("alarmed") FROM {TWIN}')],
             mappings=[value_map({0: ("NOMINAL", "#1F3B5C"), 1: ("DESVIACIÓN", CRIT)})], value_size=22,
             noValue="SIN DATOS", desc="DESVIACIÓN cuando |real − modelo| supera el umbral; vuelve a NOMINAL por debajo del 50 %."),
        stat("Desviación actual", grid(4, 0, 4, 4), [influx("A", f'SELECT last("deviation") FROM {TWIN}')],
             unit=U_LITRE, decimals=1, color_mode="value",
             thresholds=steps((None, CRIT), (-THRESHOLD_L, WARN), (-THRESHOLD_L / 2, PROCESS),
                              (THRESHOLD_L / 2, WARN), (THRESHOLD_L, CRIT)),
             desc="Nivel real − nivel modelado. Negativo: falta agua respecto a lo esperado (posible fuga)."),
        stat("Pérdida no medida", grid(8, 0, 4, 4), [influx("A", f'SELECT last("leak_lpm") FROM {TWIN}')],
             unit=U_FLOW, decimals=1, color_mode="value", graph="area",
             thresholds=steps((None, WARN), (-3, PROCESS), (3, WARN), (6, CRIT)),
             desc="Caudal que falta (positivo) o sobra (negativo) para cuadrar el balance, estimado por el observador."),
        stat("Umbral de detección", grid(12, 0, 4, 4), [influx("A", f'SELECT last("threshold") FROM {TWIN}')],
             unit=U_LITRE, decimals=0, color_mode="value", thresholds=steps((None, NEUTRAL)),
             desc="UMBRAL_L configurado en el servicio digital-twin."),
        stat("Error medio del modelo", grid(16, 0, 4, 4),
             [influx("A", f'SELECT mean("a") FROM (SELECT abs("deviation") AS "a" FROM {TWIN})')],
             unit=U_LITRE, decimals=2, color_mode="value",
             thresholds=steps((None, PROCESS), (THRESHOLD_L / 4, WARN), (THRESHOLD_L / 2, CRIT)),
             desc="Media de |real − modelo| en el rango: calidad del ajuste del gemelo."),
        stat("Detecciones", grid(20, 0, 4, 4),
             [sql("SELECT count(*) AS value FROM alarms WHERE variable = 'balance' AND $__timeFilter(ts_active)")],
             decimals=0, color_mode="value", thresholds=steps((None, PROCESS), (1, WARN)),
             desc="Alarmas de balance disparadas por el gemelo en el rango."),

        timeseries("Nivel real frente al modelo", grid(0, 4, 24, 9),
                   [twin_series("A", 'mean("level_real")', "Nivel real"),
                    twin_series("B", 'mean("level_model")', "Nivel modelo"),
                    twin_series("C", 'mean("level_model") + mean("threshold")', "Banda superior"),
                    twin_series("D", 'mean("level_model") - mean("threshold")', "Banda inferior")],
                   unit=U_LITRE, decimals=1, legend_calcs=["lastNotNull"],
                   overrides=[
                       override("Nivel real", color=fixed(PROCESS), custom__lineWidth=2),
                       override("Nivel modelo", color=fixed(MODEL), custom__fillOpacity=0,
                                custom__lineStyle={"fill": "dash", "dash": [8, 6]}),
                       override("Banda superior", color=fixed(MODEL), custom__lineWidth=0, custom__fillOpacity=10,
                                custom__fillBelowTo="Banda inferior",
                                custom__hideFrom={"legend": True, "tooltip": True, "viz": False}),
                       override("Banda inferior", color=fixed(MODEL), custom__lineWidth=0, custom__fillOpacity=0,
                                custom__hideFrom={"legend": True, "tooltip": True, "viz": False})],
                   desc=f"Nivel medido (azul) y nivel predicho por el gemelo (morado discontinuo). La banda sombreada "
                        f"es ±{THRESHOLD_L} L alrededor del modelo: salir de ella dispara la alarma de balance."),

        timeseries("Residuo (real − modelo)", grid(0, 13, 16, 8), [twin_series("A", 'mean("deviation")', "Residuo")],
                   unit=U_LITRE, decimals=2, custom={"axisCenteredZero": True, "fillOpacity": 15},
                   thresholds=steps((None, CRIT), (-THRESHOLD_L, TRANSPARENT), (THRESHOLD_L, CRIT)),
                   threshold_style="line+area", legend_calcs=["min", "max", "mean"],
                   overrides=[override("Residuo", color=fixed(MODEL))],
                   desc=f"Diferencia entre planta y modelo. Zonas rojas: fuera de ±{THRESHOLD_L} L."),
        {"id": next_id(), "type": "histogram", "title": "Distribución del residuo", "gridPos": grid(16, 13, 8, 8),
         "description": "Histograma de real − modelo en el rango: centrado y estrecho = modelo bien calibrado.",
         "datasource": INFLUX,
         "targets": [influx("A", f'SELECT "deviation" FROM {TWIN}', "Residuo")],
         "fieldConfig": {"defaults": {"color": fixed(MODEL), "unit": U_LITRE,
                                      "custom": {"fillOpacity": 60, "gradientMode": "opacity", "lineWidth": 1,
                                                 "hideFrom": {"legend": False, "tooltip": False, "viz": False}}},
                         "overrides": []},
         "options": {"bucketCount": 30, "combine": False,
                     "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []},
                     "tooltip": {"mode": "single", "sort": "none"}}},

        timeseries("Variación de nivel: esperada frente a real", grid(0, 21, 16, 8),
                   [influx("A", f'SELECT derivative(mean("level_real"), 1m) FROM {TWIN} '
                                "GROUP BY time($__interval) fill(none)", "Real"),
                    series("B", "caudal_ent", "caudal_ent"), series("C", "caudal_sal", "caudal_sal")],
                   unit="L/min", decimals=1, legend_calcs=["mean"],
                   transformations=[t_join(), t_binary("delta", "caudal_ent", "-", "caudal_sal"),
                                    t_binary("Esperada", "delta", "/", str(FLOW_DIVISOR)),
                                    t_keep("Time", "Real", "Esperada")],
                   overrides=[override("Real", color=fixed(PROCESS)),
                              override("Esperada", color=fixed(MODEL), custom__fillOpacity=0,
                                       custom__lineStyle={"fill": "dash", "dash": [8, 6]})],
                   desc="Lo que debería variar el nivel según los caudales (morado) frente a lo que varía realmente "
                        "(azul). Si divergen de forma sostenida, hay un caudal no medido."),
        table("Detecciones", grid(16, 21, 8, 8),
              [sql("""SELECT ts_active AS "Inicio", state::text AS "Estado",
  EXTRACT(EPOCH FROM COALESCE(ts_resolved, NOW()) - ts_active) AS "Duración", message AS "Mensaje"
FROM alarms WHERE variable = 'balance' ORDER BY ts_active DESC LIMIT 20""")],
              desc="Últimas 20 detecciones del gemelo con su duración.",
              overrides=[override("Inicio", unit="time:DD/MM HH:mm:ss", custom__width=120),
                         override("Estado", custom__width=100, custom__cellOptions={"type": "color-text"},
                                  mappings=[value_map({k: (k, v) for k, v in STATE_COLORS.items()})]),
                         override("Duración", unit="dtdurations", custom__width=110)]),
        text("Modelo y parámetros", grid(0, 29, 24, 5), PARAMS),
    ]
    return dashboard(UID, "03 · Gemelo digital", p, refresh="10s", time_from="now-1h",
                     description="Gemelo de balance de masas: real frente a modelo, residuo, pérdidas no medidas y detecciones.")
