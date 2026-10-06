"""05 · Explorador de datos: vista avanzada sobre todas las variables del historian."""
from lib import *  # noqa: F403

UID = "otb-explorer"

VARIABLES = [
    {"name": "variable", "label": "Variables", "type": "query", "datasource": INFLUX,
     "definition": 'SHOW TAG VALUES FROM "sensor_readings" WITH KEY = "variable"',
     "query": 'SHOW TAG VALUES FROM "sensor_readings" WITH KEY = "variable"',
     "current": {"selected": True, "text": ["nivel_x10", "caudal_ent", "caudal_sal", "velocidad"],
                 "value": ["nivel_x10", "caudal_ent", "caudal_sal", "velocidad"]},
     "hide": 0, "includeAll": True, "multi": True, "options": [], "refresh": 1, "regex": "",
     "skipUrlSync": False, "sort": 1},
    custom_var("agg", "Agregación", ["mean", "max", "min", "median", "last"], "mean"),
    {"name": "interval", "label": "Intervalo", "type": "interval", "query": "5s,10s,30s,1m,5m,15m,1h",
     "auto": True, "auto_count": 200, "auto_min": "1s",
     "current": {"selected": True, "text": "auto", "value": "$__auto_interval_interval"},
     "options": [], "hide": 0, "refresh": 2, "skipUrlSync": False},
]

VAR_FILTER = f'"variable" = \'$variable\' AND {PLC_FILTER}'
MULTI_FILTER = f'"variable" =~ /^${{variable:regex}}$/ AND {PLC_FILTER}'


def build() -> dict:
    reset_ids()
    p = [
        row("$variable", 0, repeat="variable"),
        timeseries("$variable · $agg cada $interval", grid(0, 1, 12, 7),
                   [influx("A", f'SELECT $agg("value") FROM "sensor_readings" WHERE ({VAR_FILTER}) AND $timeFilter '
                                "GROUP BY time($interval) fill(none)", "$variable")],
                   legend_calcs=["min", "max", "mean", "lastNotNull"], legend="table", legend_place="right",
                   color=fixed(PROCESS),
                   desc="Serie de la variable en unidades del contrato MQTT con la agregación e intervalo elegidos."),
        timeseries("$variable · 30 días (agregado 1 min)", grid(12, 1, 6, 7),
                   [influx("A", 'SELECT mean("mean") FROM "rp_1y"."sensor_readings_1m" '
                                f'WHERE ({VAR_FILTER}) AND $timeFilter GROUP BY time(1h) fill(none)', "$variable")],
                   legend_calcs=[], color=fixed(MODEL), timeFrom="30d",
                   desc="Tendencia larga desde la retención rp_1y (continuous query de 1 min, un año): media horaria. "
                        "Las vistas largas no leen los datos crudos a 1 Hz."),
        stat("Estadísticos de $variable", grid(18, 1, 6, 7),
             [influx("A", 'SELECT min("value") AS "Mínimo", max("value") AS "Máximo", mean("value") AS "Media", '
                          'stddev("value") AS "Desv. típica", count("value") AS "Muestras" '
                          f'FROM "sensor_readings" WHERE ({VAR_FILTER}) AND $timeFilter')],
             text_mode="value_and_name", color_mode="none", orientation="horizontal", decimals=2,
             transformations=[{"id": "renameByRegex",
                               "options": {"regex": r"sensor_readings\.(.*)", "renamePattern": "$1"}}],
             overrides=[override("Muestras", decimals=0)],
             desc="Estadística descriptiva de la variable en el rango seleccionado."),

        row("Análisis cruzado", 8),
        {"id": next_id(), "type": "xychart", "title": "Velocidad de bomba frente a caudal de salida",
         "gridPos": grid(0, 9, 12, 9), "datasource": INFLUX,
         "description": "Cada punto es la media de 1 min. Una nube estrecha indica relación estable bomba–caudal; "
                        "la dispersión creciente con el tiempo sugiere desgaste o cavitación.",
         "targets": [series("A", "velocidad", "Velocidad (%)", interval="1m"),
                     series("B", "caudal_sal", "Caudal salida", interval="1m")],
         "transformations": [{"id": "joinByField", "options": {"byField": "Time", "mode": "inner"}}],
         "fieldConfig": {"defaults": {"color": fixed(PROCESS),
                                      "custom": {"show": "points", "pointSize": {"fixed": 5}, "pointShape": "circle",
                                                 "fillOpacity": 50, "axisPlacement": "auto",
                                                 "hideFrom": {"legend": False, "tooltip": False, "viz": False}},
                                      "mappings": []}, "overrides": []},
         "options": {"mapping": "auto", "series": [{}],
                     "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []},
                     "tooltip": {"mode": "single", "sort": "none"}}},
        {"id": next_id(), "type": "xychart", "title": "Linealidad del transmisor (mA frente a nivel)",
         "gridPos": grid(12, 9, 12, 9), "datasource": INFLUX,
         "description": "Señal del transmisor frente al nivel calculado. Debe ser una recta (4 mA = vacío, "
                        "20 mA = lleno): la curvatura o dispersión indica deriva del sensor.",
         "targets": [series("A", "nivel_x10", "Nivel (L)", " / 10.0", interval="1m"),
                     series("B", "nivel_ma", "Señal (mA)", " / 100.0", interval="1m")],
         "transformations": [{"id": "joinByField", "options": {"byField": "Time", "mode": "inner"}}],
         "fieldConfig": {"defaults": {"color": fixed(MODEL),
                                      "custom": {"show": "points", "pointSize": {"fixed": 5}, "pointShape": "circle",
                                                 "fillOpacity": 50, "axisPlacement": "auto",
                                                 "hideFrom": {"legend": False, "tooltip": False, "viz": False}},
                                      "mappings": []}, "overrides": []},
         "options": {"mapping": "auto", "series": [{}],
                     "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []},
                     "tooltip": {"mode": "single", "sort": "none"}}},
        {"id": next_id(), "type": "heatmap", "title": "Distribución del nivel en el tiempo",
         "gridPos": grid(0, 18, 12, 9), "datasource": INFLUX,
         "description": "Frecuencia con la que el depósito ha estado en cada franja de nivel. Revela los puntos "
                        "de operación habituales y los extremos.",
         "targets": [series("A", "nivel_x10", "Nivel", " / 10.0", interval="1m")],
         "fieldConfig": {"defaults": {"custom": {"hideFrom": {"legend": False, "tooltip": False, "viz": False},
                                                 "scaleDistribution": {"type": "linear"}}}, "overrides": []},
         "options": {"calculate": True,
                     "calculation": {"xBuckets": {"mode": "count", "value": "40"},
                                     "yBuckets": {"mode": "count", "value": "20"}},
                     "color": {"mode": "scheme", "scheme": "Blues", "steps": 64, "exponent": 0.5,
                               "fill": PROCESS, "reverse": False},
                     "cellGap": 1, "showValue": "never", "rowsFrame": {"layout": "auto"},
                     "yAxis": {"axisPlacement": "left", "unit": U_LITRE, "reverse": False},
                     "legend": {"show": True}, "exemplars": {"color": "rgba(255,0,255,0.7)"},
                     "filterValues": {"le": 1e-9}, "tooltip": {"mode": "single", "yHistogram": True,
                                                               "showColorScale": False}}},
        bargauge("Muestras por minuto (últimos 5 min)", grid(12, 18, 6, 9),
                 [influx("A", f'SELECT count("value") / 5.0 FROM "sensor_readings" WHERE ({PLC_FILTER}) '
                              'AND time > now() - 5m GROUP BY "variable"', "$tag_variable")],
                 unit=U_NONE, min_=0, max_=60, display="basic",
                 thresholds=steps((None, CRIT), (30, WARN), (55, PROCESS)),
                 desc="Tasa de muestreo por variable. El gateway publica 1 Hz: lo esperado es 60/min."),
        bargauge("Máximo intervalo entre muestras", grid(18, 18, 6, 9),
                 [influx("A", 'SELECT max("e") FROM (SELECT elapsed("value", 1s) AS "e" FROM "sensor_readings" '
                              f'WHERE ({PLC_FILTER}) AND $timeFilter GROUP BY "variable") GROUP BY "variable"',
                         "$tag_variable")],
                 unit=U_SECONDS, min_=0, display="basic", thresholds=steps((None, PROCESS), (5, WARN), (30, CRIT)),
                 desc="Mayor separación entre dos muestras consecutivas en el rango. Nominal 1 s; > 5 s indica "
                      "un hueco en la adquisición y > 30 s una interrupción."),

        table("Datos en bruto (últimas 100 muestras por variable)", grid(0, 27, 24, 9),
              [influx("A", f'SELECT "value" FROM "sensor_readings" WHERE ({MULTI_FILTER}) AND $timeFilter '
                           'GROUP BY "variable" ORDER BY time DESC LIMIT 100', fmt="table")],
              filterable=True, footer=True,
              overrides=[override("Time", unit="time:DD/MM HH:mm:ss", custom__width=160),
                         override("variable", displayName="Variable", custom__width=160),
                         override("value", displayName="Valor")],
              desc="Muestras originales del historian para las variables seleccionadas. Exportable a CSV "
                   "desde el menú del panel (Inspect → Data)."),
    ]
    return dashboard(UID, "05 · Explorador de datos", p, refresh="1m", time_from="now-6h", variables=VARIABLES,
                     description="Exploración libre: cualquier variable, agregación e intervalo; correlaciones y calidad del dato.")
