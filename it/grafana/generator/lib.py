"""Sistema de diseno y constructores de paneles para la suite de dashboards OT-Bridge.

Todos los dashboards se generan desde codigo para mantener un lenguaje visual unico
(paleta ISA-101, unidades, navegacion, anotaciones). Ejecutar build.py tras cualquier cambio.
"""
from __future__ import annotations

import itertools

# --------------------------------------------------------------------------- datasources
INFLUX = {"type": "influxdb", "uid": "influxdb-plant"}
POSTGRES = {"type": "grafana-postgresql-datasource", "uid": "postgres-plant"}
API = {"type": "yesoreyeram-infinity-datasource", "uid": "plant-api"}

# --------------------------------------------------------------------------- paleta ISA-101
# Lo normal es neutro; el color se reserva para lo que requiere atencion.
PROCESS = "#8AB8FF"      # valor de proceso
PROCESS_2 = "#5794F2"
OK = "#73BF69"           # marcha / estado correcto (solo indicadores de estado)
WARN = "#FF9830"         # aviso
HIGH = "#FF780A"
CRIT = "#F2495C"         # critico
EMERG = "#C4162A"
MODEL = "#B877D9"        # gemelo digital / modelo
NEUTRAL = "#8E8E8E"      # normal sin relevancia
INACTIVE = "#4A4A4A"     # inactivo / apagado
YELLOW = "#FADE2A"
TRANSPARENT = "transparent"

SEVERITY_COLORS = {"CRITICAL": CRIT, "HIGH": WARN, "WARNING": YELLOW}
STATE_COLORS = {"ACTIVE": CRIT, "ACKNOWLEDGED": WARN, "RESOLVED": NEUTRAL}

# --------------------------------------------------------------------------- unidades Grafana
U_LITRE = "suffix: L"   # sufijo fijo: la unidad "litre" de Grafana reescala a mL/kL
U_FLOW = "flowlpm"
U_PERCENT = "percent"
U_MA = "mamp"
U_NONE = "none"
U_SECONDS = "s"
U_HOURS = "suffix: h"
U_FROM_NOW = "dateTimeFromNow"

PLC_FILTER = '"plc" =~ /^$plc$/'

# Escalado del contrato MQTT (docs/mqtt-contract.md): los valores son enteros crudos del PLC
FLOW = " / 10.0"            # caudal_ent / caudal_sal: l/min x10 -> l/min
NOMINAL_FLOW_LPM = 150.0    # fondo de escala del caudalimetro (PLC: 150 l/min)

_ids = itertools.count(1)


def reset_ids() -> None:
    global _ids
    _ids = itertools.count(1)


def next_id() -> int:
    return next(_ids)


# --------------------------------------------------------------------------- consultas
def where(variable: str) -> str:
    return f"\"variable\" = '{variable}' AND {PLC_FILTER}"


def influx(ref: str, query: str, alias: str | None = None, fmt: str = "time_series", **extra) -> dict:
    target = {"datasource": INFLUX, "refId": ref, "query": query, "rawQuery": True, "resultFormat": fmt}
    if alias:
        target["alias"] = alias
    target.update(extra)
    return target


def series(ref: str, variable: str, alias: str, scale: str = "", agg: str = "mean",
           interval: str = "$__interval", measurement: str = "sensor_readings", field: str = "value") -> dict:
    """Serie temporal agregada por intervalo de una variable del contrato."""
    return influx(ref, f'SELECT {agg}("{field}"){scale} FROM "{measurement}" WHERE ({where(variable)}) '
                       f"AND $timeFilter GROUP BY time({interval}) fill(none)", alias)


def latest(ref: str, variable: str, alias: str, scale: str = "") -> dict:
    """Ultimo valor de una variable dentro del rango."""
    return influx(ref, f'SELECT last("value"){scale} FROM "sensor_readings" WHERE ({where(variable)}) AND $timeFilter',
                  alias)


def sql(sql_text: str, ref: str = "A", fmt: str = "table") -> dict:
    return {"datasource": POSTGRES, "refId": ref, "format": fmt, "rawQuery": True, "editorMode": "code",
            "rawSql": sql_text}


def api(ref: str, url: str, root: str = "", columns: list[tuple[str, str, str]] | None = None) -> dict:
    """Consulta JSON a la API REST via Infinity. columns = [(selector, titulo, tipo)]."""
    return {"datasource": API, "refId": ref, "type": "json", "source": "url", "format": "table",
            "parser": "backend", "url": url, "url_options": {"method": "GET", "data": ""},
            "root_selector": root,
            "columns": [{"selector": s, "text": t, "type": ty} for s, t, ty in (columns or [])]}


# --------------------------------------------------------------------------- fieldConfig
def steps(*pairs) -> dict:
    """Umbrales absolutos: steps((None, color), (valor, color), ...) en orden ascendente."""
    values = [v for v, _ in pairs if v is not None]
    assert values == sorted(values), f"Umbrales no ascendentes: {values}"
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in pairs]}


def value_map(mapping: dict) -> dict:
    """{valor: (texto, color)} -> mapping de valores."""
    return {"type": "value", "options": {str(k): {"text": t, "color": c, "index": i}
                                         for i, (k, (t, c)) in enumerate(mapping.items())}}


def range_map(ranges: list[tuple[float | None, float | None, str, str]]) -> list[dict]:
    return [{"type": "range", "options": {"from": lo, "to": hi, "result": {"text": t, "color": c, "index": i}}}
            for i, (lo, hi, t, c) in enumerate(ranges)]


def override(name: str, regex: bool = False, **props) -> dict:
    matcher = {"id": "byRegexp" if regex else "byName", "options": name}
    return {"matcher": matcher, "properties": [{"id": k.replace("__", "."), "value": v} for k, v in props.items()]}


def fixed(color: str) -> dict:
    return {"mode": "fixed", "fixedColor": color}


def link(title: str, uid: str) -> dict:
    return {"title": title, "url": f"/d/{uid}?${{__url_time_range}}&${{plc:queryparam}}", "targetBlank": False}


def grid(x: int, y: int, w: int, h: int) -> dict:
    return {"x": x, "y": y, "w": w, "h": h}


# --------------------------------------------------------------------------- paneles
def _base(kind: str, title: str, pos: dict, targets: list[dict], desc: str) -> dict:
    return {"id": next_id(), "type": kind, "title": title, "description": desc, "gridPos": pos,
            "datasource": targets[0]["datasource"] if targets else INFLUX, "targets": targets}


def row(title: str, y: int, repeat: str | None = None) -> dict:
    panel = {"id": next_id(), "type": "row", "title": title, "collapsed": False, "gridPos": grid(0, y, 24, 1),
             "panels": []}
    if repeat:
        panel["repeat"] = repeat
    return panel


def stat(title: str, pos: dict, targets: list[dict], *, unit: str = U_NONE, thresholds: dict | None = None,
         mappings: list | None = None, decimals: int | None = None, desc: str = "", color_mode: str = "background",
         graph: str = "none", text_mode: str = "value", links: list | None = None, overrides: list | None = None,
         calc: str = "lastNotNull", fields: str = "", value_size: int | None = None, orientation: str = "auto",
         color: dict | None = None, min_: float | None = None, max_: float | None = None,
         transformations: list | None = None, **extra) -> dict:
    defaults = {"unit": unit, "color": color or {"mode": "thresholds"},
                "thresholds": thresholds or steps((None, NEUTRAL)), "mappings": mappings or [], "links": links or []}
    if decimals is not None:
        defaults["decimals"] = decimals
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    panel = _base("stat", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": defaults, "overrides": overrides or []}
    panel["options"] = {"colorMode": color_mode, "graphMode": graph, "justifyMode": "center",
                        "orientation": orientation, "textMode": text_mode, "wideLayout": True,
                        "showPercentChange": False,
                        "reduceOptions": {"calcs": [calc], "fields": fields, "values": False}}
    if value_size:
        panel["options"]["text"] = {"valueSize": value_size}
    if transformations:
        panel["transformations"] = transformations
    panel.update(extra)
    return panel


def gauge(title: str, pos: dict, targets: list[dict], *, unit: str, min_: float, max_: float, thresholds: dict,
          decimals: int = 1, desc: str = "", links: list | None = None, mappings: list | None = None,
          overrides: list | None = None, **extra) -> dict:
    panel = _base("gauge", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": {"unit": unit, "min": min_, "max": max_, "decimals": decimals,
                                         "color": {"mode": "thresholds"}, "thresholds": thresholds,
                                         "mappings": mappings or [], "links": links or []},
                            "overrides": overrides or []}
    panel["options"] = {"showThresholdMarkers": True, "showThresholdLabels": False, "minVizHeight": 75,
                        "minVizWidth": 75, "sizing": "auto", "orientation": "auto",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}
    panel.update(extra)
    return panel


def bargauge(title: str, pos: dict, targets: list[dict], *, unit: str = U_NONE, thresholds: dict | None = None,
             desc: str = "", overrides: list | None = None, min_: float | None = 0, max_: float | None = None,
             display: str = "basic", orientation: str = "horizontal", transformations: list | None = None,
             values: bool = False, **extra) -> dict:
    defaults = {"unit": unit, "color": {"mode": "thresholds"}, "thresholds": thresholds or steps((None, PROCESS)),
                "mappings": []}
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    panel = _base("bargauge", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": defaults, "overrides": overrides or []}
    panel["options"] = {"orientation": orientation, "displayMode": display, "showUnfilled": True,
                        "valueMode": "color", "namePlacement": "auto", "sizing": "auto", "minVizHeight": 16,
                        "minVizWidth": 8, "maxVizHeight": 300,
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": values}}
    if transformations:
        panel["transformations"] = transformations
    panel.update(extra)
    return panel


TS_DEFAULTS = {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 8, "gradientMode": "opacity",
               "lineInterpolation": "smooth", "showPoints": "never", "pointSize": 4, "spanNulls": 60000,
               "axisPlacement": "auto", "axisLabel": "", "axisColorMode": "text", "axisBorderShow": False,
               "axisCenteredZero": False, "scaleDistribution": {"type": "linear"}, "barAlignment": 0,
               "stacking": {"group": "A", "mode": "none"}, "thresholdsStyle": {"mode": "off"},
               "insertNulls": False, "lineStyle": {"fill": "solid"},
               "hideFrom": {"legend": False, "tooltip": False, "viz": False}}


def timeseries(title: str, pos: dict, targets: list[dict], *, unit: str = U_NONE, desc: str = "",
               overrides: list | None = None, thresholds: dict | None = None, threshold_style: str = "off",
               legend_calcs: list[str] | None = None, legend: str = "list", legend_place: str = "bottom",
               transformations: list | None = None, min_: float | None = None, max_: float | None = None,
               custom: dict | None = None, color: dict | None = None, decimals: int | None = None,
               stacking: str = "none", **extra) -> dict:
    custom_cfg = dict(TS_DEFAULTS, thresholdsStyle={"mode": threshold_style}, stacking={"group": "A", "mode": stacking})
    custom_cfg.update(custom or {})
    defaults = {"unit": unit, "custom": custom_cfg, "color": color or {"mode": "palette-classic"},
                "thresholds": thresholds or steps((None, NEUTRAL)), "mappings": []}
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    if decimals is not None:
        defaults["decimals"] = decimals
    panel = _base("timeseries", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": defaults, "overrides": overrides or []}
    panel["options"] = {"legend": {"displayMode": legend, "placement": legend_place, "showLegend": True,
                                   "calcs": legend_calcs if legend_calcs is not None else ["lastNotNull"]},
                        "tooltip": {"mode": "multi", "sort": "none"}}
    if transformations:
        panel["transformations"] = transformations
    panel.update(extra)
    return panel


def table(title: str, pos: dict, targets: list[dict], *, desc: str = "", overrides: list | None = None,
          transformations: list | None = None, sort: list | None = None, filterable: bool = False,
          footer: bool = False, no_value: str = "Sin registros", **extra) -> dict:
    panel = _base("table", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"},
                                                    "inspect": False, "filterable": filterable},
                                         "color": {"mode": "thresholds"}, "thresholds": steps((None, NEUTRAL)),
                                         "mappings": [], "noValue": no_value},
                            "overrides": overrides or []}
    panel["options"] = {"cellHeight": "sm", "showHeader": True, "sortBy": sort or [],
                        "footer": {"show": footer, "reducer": ["count"], "fields": "", "countRows": footer}}
    if transformations:
        panel["transformations"] = transformations
    panel.update(extra)
    return panel


def _thresholds_from(mappings: list) -> dict:
    """Umbrales equivalentes a un mapping de valores numericos: el color no depende de que el mapping case."""
    options = mappings[0]["options"] if mappings and mappings[0]["type"] == "value" else {}
    pairs = sorted((float(k), v["color"]) for k, v in options.items())
    if not pairs:
        return steps((None, INACTIVE))
    return steps((None, pairs[0][1]), *[(k, c) for k, c in pairs[1:]])


def state_timeline(title: str, pos: dict, targets: list[dict], *, mappings: list, desc: str = "",
                   thresholds: dict | None = None, overrides: list | None = None, **extra) -> dict:
    panel = _base("state-timeline", title, pos, targets, desc)
    panel["fieldConfig"] = {"defaults": {"custom": {"fillOpacity": 80, "lineWidth": 0,
                                                    "hideFrom": {"legend": False, "tooltip": False, "viz": False}},
                                         "color": {"mode": "thresholds"},
                                         "thresholds": thresholds or _thresholds_from(mappings),
                                         "mappings": mappings},
                            "overrides": overrides or []}
    panel["options"] = {"showValue": "never", "rowHeight": 0.8, "mergeValues": True, "alignValue": "left",
                        "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "single", "sort": "none"}}
    panel.update(extra)
    return panel


def text(title: str, pos: dict, content: str, desc: str = "") -> dict:
    return {"id": next_id(), "type": "text", "title": title, "description": desc, "gridPos": pos,
            "options": {"mode": "markdown", "content": content,
                        "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False}}}


# --------------------------------------------------------------------------- transformaciones
def t_join() -> dict:
    """Une series por tiempo conservando cada campo. No usar merge: InfluxDB llama "Value" a todos los
    campos y merge los fusionaria en una sola columna."""
    return {"id": "joinByField", "options": {"byField": "Time", "mode": "outer"}}


def t_binary(alias: str, left: str, op: str, right: str, replace: bool = False) -> dict:
    return {"id": "calculateField", "options": {"alias": alias, "mode": "binary", "replaceFields": replace,
                                                "binary": {"left": left, "operator": op, "right": right}}}


def t_keep(*names: str) -> dict:
    return {"id": "filterFieldsByName", "options": {"include": {"names": list(names)}}}


def t_organize(rename: dict | None = None, exclude: list | None = None, order: list | None = None) -> dict:
    return {"id": "organize", "options": {"renameByName": rename or {},
                                         "excludeByName": {k: True for k in (exclude or [])},
                                         "indexByName": {k: i for i, k in enumerate(order or [])}}}


# --------------------------------------------------------------------------- dashboard
PLC_VAR = {"name": "plc", "label": "PLC", "type": "query", "datasource": INFLUX,
           "definition": 'SHOW TAG VALUES FROM "sensor_readings" WITH KEY = "plc"',
           "query": 'SHOW TAG VALUES FROM "sensor_readings" WITH KEY = "plc"',
           "current": {"selected": True, "text": "plc01", "value": "plc01"},
           "hide": 0, "includeAll": False, "multi": False, "options": [], "refresh": 1, "regex": "",
           "skipUrlSync": False, "sort": 1}


def custom_var(name: str, label: str, values: list[str], default: str | list[str], multi: bool = False,
               include_all: bool = False) -> dict:
    current = default if isinstance(default, list) else [default]
    return {"name": name, "label": label, "type": "custom", "query": ",".join(values),
            "current": {"selected": True, "text": current if multi else current[0],
                        "value": current if multi else current[0]},
            "options": [{"text": v, "value": v, "selected": v in current} for v in values],
            "multi": multi, "includeAll": include_all, "hide": 0, "skipUrlSync": False}


def _alarm_annotation(severity: str, color: str) -> dict:
    return {"name": f"Alarmas {severity}", "datasource": POSTGRES, "enable": severity != "WARNING",
            "hide": True, "iconColor": color,
            "target": {"refId": "Anno", "format": "table", "rawQuery": True, "editorMode": "code",
                       "rawSql": ("SELECT ts_active AS time, COALESCE(ts_resolved, NOW()) AS timeend, "
                                  "variable || ': ' || COALESCE(message, '') AS text, severity::text AS tags "
                                  f"FROM alarms WHERE severity = '{severity}' AND $__timeFilter(ts_active)")}}


ANNOTATIONS = {"list": [
    {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": True,
     "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"},
    {"name": "PLC offline", "datasource": INFLUX, "enable": True, "hide": True, "iconColor": EMERG,
     "target": {"refId": "Anno", "rawQuery": True, "limit": 100, "matchAny": False, "tags": [], "type": "influxdb",
                "query": 'SELECT "online" FROM "plc_status" WHERE ("online" = 0 AND "plc" =~ /^$plc$/) AND $timeFilter'}},
    _alarm_annotation("CRITICAL", CRIT),
    _alarm_annotation("HIGH", WARN),
    _alarm_annotation("WARNING", YELLOW),
]}

NAV_LINKS = [{"title": "OT-Bridge", "type": "dashboards", "tags": ["otbridge"], "asDropdown": False,
              "includeVars": True, "keepTime": True, "targetBlank": False, "icon": "external link", "tooltip": "",
              "url": ""}]


def dashboard(uid: str, title: str, panels: list[dict], *, refresh: str, time_from: str,
              variables: list[dict] | None = None, description: str = "") -> dict:
    return {
        "uid": uid, "title": title, "description": description, "tags": ["otbridge"],
        "editable": True, "graphTooltip": 1, "id": None, "links": NAV_LINKS, "liveNow": False,
        "refresh": refresh, "schemaVersion": 39, "version": 1, "timezone": "browser",
        "fiscalYearStartMonth": 0, "weekStart": "monday",
        "time": {"from": time_from, "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m"]},
        "templating": {"list": [PLC_VAR] + (variables or [])},
        "annotations": ANNOTATIONS,
        "panels": panels,
    }
