"""Genera el proyecto FUXA completo (SCADA OT) y lo valida.

Uso:  python ot/scada/hmi/generator/build.py [--target sandbox|plant]
Salida: ot/scada/hmi/build/project-<target>.json  (sin secretos: las credenciales MQTT las fija deploy.py)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import HEADER, TEXT, perm, SUPERVISE  # noqa: E402
from model import alarms, charts, decode_script, devices  # noqa: E402
from views import control, diagnostics, dialogs, overview, process, trends, alarms as alarms_view  # noqa: E402
from views.common import VIEW_IDS  # noqa: E402

TARGETS = {
    # El sandbox apunta al simulador del PLC y al broker local; la planta al OpenPLC real y al broker IT
    # (mismo host: mosquitto:1883; dos hosts: scripts/fuxa_set_broker.py fija la direccion del host IT).
    "sandbox": {"plc": "plc-sim:5502", "mqtt": "mqtt://host.docker.internal:1883"},
    "plant": {"plc": "openplc-runtime:502", "mqtt": "mqtt://mosquitto:1883"},
}


def layout() -> dict:
    nav = [("Visión general", "overview", "dashboard", 0), ("Proceso", "process", "account_tree", 0),
           ("Mando", "control", "touch_app", 0), ("Alarmas", "alarms", "notifications", 0),
           ("Tendencias", "trends", "show_chart", 0),
           ("Diagnóstico", "diagnostics", "build", perm(show=SUPERVISE, enable=SUPERVISE))]
    return {
        "autoresize": True, "start": VIEW_IDS["overview"], "showdev": False, "zoom": "disabled",
        "inputdialog": "false", "hidenavigation": False, "theme": "", "loginonstart": False,
        "navigation": {"mode": "over", "type": "block", "bkcolor": HEADER, "fgcolor": TEXT,
                       "items": [{"text": t, "view": VIEW_IDS[k], "link": "", "icon": i, "image": "",
                                  "permission": p, "permissionRoles": {"show": [], "enabled": []}}
                                 for t, k, i, p in nav], "logo": False},
        "header": {"title": "BALSA TK-101 · SCADA OT", "alarms": "float", "infos": "float", "bkcolor": HEADER,
                   "fgcolor": TEXT, "height": 46, "buttonHeight": 36, "fontFamily": "Roboto, sans-serif",
                   "fontSize": 14, "items": [], "itemsAnchor": "left", "loginInfo": "both",
                   "dateTimeDisplay": "dd/MM/yyyy HH:mm:ss", "language": "nothing"},
    }


def build(target: str) -> dict:
    views = [overview.build(), process.build(), control.build(), alarms_view.build(), trends.build(),
             diagnostics.build(), *dialogs.build()]
    prj = {
        "version": "1.00",
        "devices": devices(TARGETS[target]["plc"], TARGETS[target]["mqtt"]),
        "hmi": {"views": [v.to_json() for v in views], "layout": layout()},
        "alarms": alarms(), "scripts": [decode_script()], "charts": charts(),
        "notifications": [], "reports": [], "texts": [], "graphs": [],
        "server": {"id": "0", "name": "FUXA Server", "type": "FuxaServer", "property": {}},
        "ar": {"enabled": False, "markers": []},
    }
    validate(prj)
    return prj


def validate(prj: dict) -> None:
    """Coherencia interna: referencias a tags, ids SVG, duplicados, vistas enlazadas."""
    errors = []
    tags = {tid: t for d in prj["devices"].values() for tid, t in d["tags"].items()}
    names = [t["name"] for t in tags.values()]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        errors.append(f"tags con nombre duplicado: {sorted(dup)}")
    view_ids = {v["id"] for v in prj["hmi"]["views"]}
    chart_ids = {c["id"] for c in prj["charts"]}

    def check_tag(ref, where):
        if ref and ref not in tags:
            errors.append(f"{where}: tag inexistente {ref}")

    for v in prj["hmi"]["views"]:
        svg_ids = set(re.findall(r'<g id="([^"]+)" type="svg-ext', v["svgcontent"]))
        if svg_ids != set(v["items"]):
            errors.append(f"{v['name']}: items sin SVG {set(v['items']) - svg_ids} / SVG sin item {svg_ids - set(v['items'])}")
        for it in v["items"].values():
            p = it.get("property") or {}
            where = f"{v['name']}/{it['name']}"
            check_tag(p.get("variableId"), where)
            for a in p.get("actions", []):
                check_tag(a.get("variableId"), where)
            for e in p.get("events", []):
                if e["action"] in ("ondialog", "onpage") and e["actparam"] not in view_ids:
                    errors.append(f"{where}: vista inexistente {e['actparam']}")
                if e["action"] == "onSetValue" and not p.get("variableId"):
                    errors.append(f"{where}: onSetValue sin tag")
            if it["type"] == "svg-ext-html_chart" and p.get("id") not in chart_ids:
                errors.append(f"{where}: grafica inexistente {p.get('id')}")
            writes = (it["type"] in ("svg-ext-html_input", "svg-ext-html_slider") or
                      any(e["action"] == "onSetValue" for e in p.get("events", [])))
            if writes and not p.get("permission"):
                errors.append(f"{where}: mando sin permiso (seria operable por cualquiera)")
    for a in prj["alarms"]:
        check_tag(a["property"]["variableId"], f"alarma {a['name']}")
    for c in prj["charts"]:
        for ln in c["lines"]:
            check_tag(ln["id"], f"grafica {c['name']}")
            if not tags.get(ln["id"], {}).get("daq", {}).get("enabled"):
                errors.append(f"grafica {c['name']}: {ln['name']} sin DAQ (no tendra historico)")
    for item in prj["hmi"]["layout"]["navigation"]["items"]:
        if item["view"] not in view_ids:
            errors.append(f"navegacion: vista inexistente {item['view']}")
    if errors:
        raise SystemExit("VALIDACION FALLIDA:\n  " + "\n  ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=TARGETS, default="sandbox")
    args = parser.parse_args()
    prj = build(args.target)
    out = HERE.parent / "build" / f"project-{args.target}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(prj, ensure_ascii=False, indent=1), encoding="utf-8")
    items = sum(len(v["items"]) for v in prj["hmi"]["views"])
    tags = sum(len(d["tags"]) for d in prj["devices"].values())
    print(f"{out.name}: {len(prj['hmi']['views'])} vistas, {items} controles, {tags} tags, "
          f"{len(prj['alarms'])} alarmas, {len(prj['charts'])} graficas - validacion OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
