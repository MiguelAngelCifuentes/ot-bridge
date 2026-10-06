"""02 · Alarmas: gestion de alarmas con indicadores ISA-18.2 y filtros dinamicos."""
from lib import *  # noqa: F403

UID = "otb-alarms"

F = ("severity::text IN (${severity:sqlstring}) AND state::text IN (${state:sqlstring}) "
     "AND variable IN (${alarm_var:sqlstring})")
F_RANGE = F + " AND $__timeFilter(ts_active)"
SEV_ORDER = "CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END"

SEV_CELL = dict(custom__cellOptions={"type": "color-background", "mode": "basic"},
                mappings=[value_map({k: (k, v) for k, v in SEVERITY_COLORS.items()})])
STATE_CELL = dict(custom__cellOptions={"type": "color-text"},
                  mappings=[value_map({k: (k, v) for k, v in STATE_COLORS.items()})])

VARIABLES = [
    custom_var("severity", "Severidad", ["CRITICAL", "HIGH", "WARNING"], ["CRITICAL", "HIGH", "WARNING"],
               multi=True, include_all=False),
    custom_var("state", "Estado", ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"], ["ACTIVE", "ACKNOWLEDGED", "RESOLVED"],
               multi=True, include_all=False),
    {"name": "alarm_var", "label": "Variable", "type": "query", "datasource": POSTGRES,
     "definition": "SELECT DISTINCT variable FROM alarms ORDER BY 1",
     "query": "SELECT DISTINCT variable FROM alarms ORDER BY 1",
     "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
     "hide": 0, "includeAll": True, "multi": True, "options": [], "refresh": 2, "regex": "",
     "skipUrlSync": False, "sort": 1},
]


def _kpi(title: str, x: int, sql_text: str, desc: str, unit: str = U_NONE, thr: dict | None = None,
         decimals: int = 0) -> dict:
    return stat(title, grid(x, 0, 4, 4), [sql(sql_text)], unit=unit, decimals=decimals, color_mode="value",
                thresholds=thr or steps((None, PROCESS)), desc=desc, noValue="—")


def build() -> dict:
    reset_ids()
    p = [
        _kpi("Activas", 0, f"SELECT count(*) AS value FROM alarms WHERE {F} AND state <> 'RESOLVED'",
             "Alarmas no resueltas (con los filtros aplicados).", thr=steps((None, NEUTRAL), (1, WARN))),
        _kpi("Sin reconocer", 4, f"SELECT count(*) AS value FROM alarms WHERE {F} AND state = 'ACTIVE' AND ts_ack IS NULL",
             "Alarmas activas que ningún operador ha reconocido todavía.", thr=steps((None, NEUTRAL), (1, CRIT))),
        _kpi("MTTA", 8, f"SELECT avg(EXTRACT(EPOCH FROM ts_ack - ts_active)) AS value FROM alarms "
                        f"WHERE {F_RANGE} AND ts_ack IS NOT NULL",
             "Tiempo medio hasta el reconocimiento (Mean Time To Acknowledge) en el rango.", unit="dtdurations"),
        _kpi("MTTR", 12, f"SELECT avg(EXTRACT(EPOCH FROM ts_resolved - ts_active)) AS value FROM alarms "
                         f"WHERE {F_RANGE} AND ts_resolved IS NOT NULL",
             "Tiempo medio hasta la resolución (Mean Time To Resolve) en el rango.", unit="dtdurations"),
        _kpi("Tasa de alarmas", 16,
             f"SELECT count(*) / GREATEST(EXTRACT(EPOCH FROM ($__timeTo()::timestamptz - $__timeFrom()::timestamptz)) "
             f"/ 3600.0, 1) AS value FROM alarms WHERE {F_RANGE}",
             "Alarmas por hora en el rango. Referencia ISA-18.2: ≤ 6/h gestionable, > 10/h sobrecarga del operador.",
             unit="alarmas/h", decimals=2, thr=steps((None, PROCESS), (6, WARN), (10, CRIT))),
        _kpi("Chattering", 20,
             "WITH a AS (SELECT ts_active, LAG(COALESCE(ts_resolved, ts_active)) OVER "
             f"(PARTITION BY variable, severity ORDER BY ts_active) AS prev_end FROM alarms WHERE {F_RANGE}) "
             "SELECT COALESCE(100.0 * count(*) FILTER (WHERE ts_active - prev_end < INTERVAL '60 seconds') "
             "/ NULLIF(count(*), 0), 0) AS value FROM a",
             "Porcentaje de activaciones que se repiten menos de 60 s después de la anterior de la misma variable. "
             "> 5 % indica umbrales sin histéresis o banda muerta insuficiente.",
             unit=U_PERCENT, decimals=1, thr=steps((None, PROCESS), (5, WARN), (20, CRIT))),

        table("Alarmas activas", grid(0, 4, 24, 7),
              [sql(f"""SELECT
  severity::text AS "Severidad", variable AS "Variable", message AS "Mensaje", state::text AS "Estado",
  ts_active AS "Activada", EXTRACT(EPOCH FROM NOW() - ts_active) AS "Antigüedad",
  ts_ack AS "Reconocida", ack_by AS "Operador"
FROM alarms WHERE {F} AND state <> 'RESOLVED'
ORDER BY {SEV_ORDER}, ts_active""")],
              desc="Alarmas pendientes. Orden: severidad y después antigüedad (la más antigua primero).",
              no_value="Sin alarmas activas",
              overrides=[override("Severidad", custom__width=110, **SEV_CELL),
                         override("Estado", custom__width=130, **STATE_CELL),
                         override("Variable", custom__width=110),
                         override("Activada", unit="time:DD/MM HH:mm:ss", custom__width=140),
                         override("Reconocida", unit="time:DD/MM HH:mm:ss", custom__width=140, noValue="—"),
                         override("Operador", noValue="—"),
                         override("Antigüedad", unit="dtdurations", custom__width=160,
                                  custom__cellOptions={"type": "color-text"},
                                  thresholds=steps((None, NEUTRAL), (600, WARN), (3600, CRIT)))]),

        timeseries("Alarmas por hora", grid(0, 11, 16, 8),
                   [sql(f"SELECT $__timeGroupAlias(ts_active, '1h'), severity::text AS metric, count(*) AS value "
                        f"FROM alarms WHERE {F_RANGE} GROUP BY 1, 2 ORDER BY 1", fmt="time_series")],
                   unit=U_NONE, decimals=0, stacking="normal", legend_calcs=["sum"],
                   custom={"drawStyle": "bars", "fillOpacity": 80, "lineWidth": 0, "gradientMode": "none",
                           "barAlignment": 1},
                   thresholds=steps((None, TRANSPARENT), (6, WARN)), threshold_style="dashed",
                   overrides=[override(k, color=fixed(v)) for k, v in SEVERITY_COLORS.items()],
                   desc="Activaciones por hora apiladas por severidad. Línea discontinua: 6 alarmas/h (ISA-18.2)."),
        {"id": next_id(), "type": "piechart", "title": "Distribución por severidad", "gridPos": grid(16, 11, 8, 8),
         "description": "Reparto de las alarmas del rango por severidad.", "datasource": POSTGRES,
         "targets": [sql(f'SELECT severity::text AS "Severidad", count(*) AS "Alarmas" FROM alarms WHERE {F_RANGE} '
                         f"GROUP BY severity ORDER BY {SEV_ORDER}")],
         "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}, "mappings": [], "unit": U_NONE},
                         "overrides": [override(k, color=fixed(v)) for k, v in SEVERITY_COLORS.items()]},
         "options": {"pieType": "donut", "displayLabels": ["percent"],
                     "legend": {"showLegend": True, "displayMode": "table", "placement": "right", "values": ["value"]},
                     "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                     "tooltip": {"mode": "single", "sort": "none"}}},

        bargauge("Bad actors (top 10)", grid(0, 19, 8, 8),
                 [sql(f'SELECT variable AS "Variable", count(*) AS "Alarmas" FROM alarms WHERE {F_RANGE} '
                      "GROUP BY variable ORDER BY 2 DESC LIMIT 10")],
                 values=True, display="gradient", thresholds=steps((None, PROCESS), (10, WARN), (25, CRIT)),
                 desc="Variables que más alarmas generan: primeras candidatas a revisar umbrales (ISA-18.2)."),
        {"id": next_id(), "type": "barchart", "title": "Alarmas por hora del día", "gridPos": grid(8, 19, 8, 8),
         "description": "Activaciones agrupadas por hora local (Europe/Madrid): patrones por turno.",
         "datasource": POSTGRES,
         "targets": [sql(f"""SELECT LPAD(h::text, 2, '0') || 'h' AS "Hora", COALESCE(c, 0) AS "Alarmas"
FROM generate_series(0, 23) AS h
LEFT JOIN (SELECT EXTRACT(HOUR FROM ts_active AT TIME ZONE 'Europe/Madrid')::int AS hh, count(*) AS c
           FROM alarms WHERE {F_RANGE} GROUP BY 1) x ON x.hh = h
ORDER BY h""")],
         "fieldConfig": {"defaults": {"color": fixed(PROCESS), "custom": {"fillOpacity": 70, "lineWidth": 0,
                                                                          "gradientMode": "opacity"},
                                      "mappings": [], "unit": U_NONE, "decimals": 0}, "overrides": []},
         "options": {"orientation": "vertical", "xField": "Hora", "showValue": "never", "barWidth": 0.8,
                     "groupWidth": 0.7, "xTickLabelSpacing": 100, "stacking": "none",
                     "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                     "tooltip": {"mode": "single", "sort": "none"}}},
        table("Chattering por variable", grid(16, 19, 8, 8),
              [sql(f"""WITH a AS (
  SELECT variable, ts_active,
         EXTRACT(EPOCH FROM ts_active - LAG(COALESCE(ts_resolved, ts_active))
                 OVER (PARTITION BY variable, severity ORDER BY ts_active)) AS gap
  FROM alarms WHERE {F_RANGE})
SELECT variable AS "Variable", count(*) AS "Activaciones",
       count(*) FILTER (WHERE gap < 60) AS "Repetidas < 60 s",
       min(gap) AS "Intervalo mínimo"
FROM a GROUP BY variable ORDER BY 3 DESC, 2 DESC""")],
              desc="Activaciones por variable y cuántas se repiten en menos de 60 s (chattering).",
              overrides=[override("Intervalo mínimo", unit="dtdurations", noValue="—"),
                         override("Variable", custom__width=110),
                         override("Repetidas < 60 s", custom__cellOptions={"type": "color-text"},
                                  thresholds=steps((None, NEUTRAL), (1, WARN)))]),

        table("Histórico de alarmas", grid(0, 27, 24, 10),
              [sql(f"""SELECT
  ts_active AS "Activada", severity::text AS "Severidad", variable AS "Variable", message AS "Mensaje",
  state::text AS "Estado", ts_ack AS "Reconocida", ack_by AS "Operador",
  EXTRACT(EPOCH FROM ts_ack - ts_active) AS "T. reconocimiento",
  ts_resolved AS "Resuelta", EXTRACT(EPOCH FROM COALESCE(ts_resolved, NOW()) - ts_active) AS "Duración"
FROM alarms WHERE {F_RANGE}
ORDER BY ts_active DESC LIMIT 500""")],
              filterable=True, footer=True,
              desc="Ciclo de vida completo de cada alarma del rango (máx. 500). Filtrable por columna.",
              overrides=[override("Severidad", custom__width=110, **SEV_CELL),
                         override("Estado", custom__width=130, **STATE_CELL),
                         override("Activada", unit="time:DD/MM/YY HH:mm:ss", custom__width=150),
                         override("Reconocida", unit="time:DD/MM HH:mm:ss", custom__width=130, noValue="—"),
                         override("Operador", noValue="—"),
                         override("Resuelta", unit="time:DD/MM HH:mm:ss", custom__width=130, noValue="—"),
                         override("T. reconocimiento", unit="dtdurations", noValue="—"),
                         override("Duración", unit="dtdurations")]),
    ]
    return dashboard(UID, "02 · Alarmas", p, refresh="10s", time_from="now-7d", variables=VARIABLES,
                     description="Gestión de alarmas: pendientes, KPIs ISA-18.2, bad actors, chattering e histórico.")
