"""Ejecuta todas las consultas de los dashboards provisionados contra /api/ds/query de Grafana.

Falla (exit 1) si alguna consulta devuelve error o un panel no devuelve datos.
Uso:  python scripts/check_dashboards.py [uid ...]      (GRAFANA_PASSWORD en el entorno o en .env)
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAFANA = os.getenv("GRAFANA_URL", "http://127.0.0.1:3000")
# Paneles cuyo vacio es un estado valido (p. ej. sin alarmas activas)
MAY_BE_EMPTY = re.compile(r"Alarmas activas$|Chattering|Detecciones", re.IGNORECASE)
# Valores de variables multi-valor para la comprobacion (formato :sqlstring)
VAR_DEFAULTS = {"plc": "plc01", "severity": "'CRITICAL','HIGH','WARNING'",
                "state": "'ACTIVE','ACKNOWLEDGED','RESOLVED'",
                "alarm_var": "'estado','nivel_x10','velocidad','balance'"}


def password() -> str:
    if os.getenv("GRAFANA_PASSWORD"):
        return os.environ["GRAFANA_PASSWORD"]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GRAFANA_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GRAFANA_PASSWORD no definido")


AUTH = "Basic " + base64.b64encode(f"admin:{password()}".encode()).decode()


def request(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GRAFANA + path, data, {"Content-Type": "application/json", "Authorization": AUTH})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as exc:
        return json.load(exc)


def interpolate(text: str, variables: dict[str, str]) -> str:
    for name, value in variables.items():
        text = re.sub(r"\$\{" + name + r"(:[a-z]+)?\}|\$" + name + r"\b", value, text)
    return text


def dashboard_vars(dash: dict) -> dict[str, str]:
    values = {}
    for var in dash["templating"]["list"]:
        current = var.get("current", {}).get("value")
        if isinstance(current, list):
            current = current[0] if current else ""
        values[var["name"]] = str(current or "")
    values.update(VAR_DEFAULTS)
    return values


def check(uid: str) -> bool:
    dash = request(f"/api/dashboards/uid/{uid}")["dashboard"]
    variables = dashboard_vars(dash)
    ok = True
    print(f"\n=== {dash['title']} ({uid})")
    for panel in dash["panels"]:
        if panel["type"] in ("row", "text"):
            continue
        targets = []
        for target in panel.get("targets", []):
            t = json.loads(interpolate(json.dumps(target), variables | {"__interval": "10s", "interval": "1m"}))
            targets.append(t)
        if not targets:
            continue
        span = panel.get("timeFrom") or dash["time"]["from"].replace("now-", "")
        res = request("/api/ds/query", {"queries": targets, "from": f"now-{span}", "to": "now"})
        errors = [f"{ref}: {r['error']}" for ref, r in res.get("results", {}).items() if r.get("error")]
        if "results" not in res:
            errors.append(res.get("message", "respuesta inesperada"))
        rows = sum(len(fr["data"]["values"][0]) if fr["data"]["values"] else 0
                   for r in res.get("results", {}).values() for fr in r.get("frames", []))
        empty = rows == 0 and not MAY_BE_EMPTY.search(panel["title"])
        status = "ERROR" if errors else ("VACÍO" if empty else "ok")
        ok &= status == "ok"
        print(f"  [{status:5}] {panel['title']:<45} filas={rows} {'; '.join(errors)[:200]}")
    return ok


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def check_plugins() -> bool:
    """El backend de un plugin puede responder aunque su frontend no cargue en esta version de Grafana:
    se compara el minimo declarado por cada plugin externo con la version en ejecucion."""
    grafana = _version(request("/api/health")["version"])
    ok = True
    print(f"=== Plugins (Grafana {'.'.join(map(str, grafana))})")
    for plugin in request("/api/plugins?core=0"):
        requirement = request(f"/api/plugins/{plugin['id']}/settings").get("dependencies", {}).get("grafanaDependency", "")
        minimum = re.match(r"\s*>=\s*([\d.]+)", requirement)
        compatible = not minimum or grafana >= _version(minimum.group(1))
        ok &= compatible
        print(f"  [{'ok' if compatible else 'INCOMPATIBLE':5}] {plugin['id']} {plugin['info']['version']} (requiere {requirement or '-'})")
    return ok


def main(uids: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # consola Windows cp1252
    if not uids:
        uids = [d["uid"] for d in request("/api/search?tag=otbridge")]
    results = [check_plugins()] + [check(uid) for uid in sorted(uids)]
    print("\nRESULTADO:", "OK" if all(results) else "HAY PROBLEMAS")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
