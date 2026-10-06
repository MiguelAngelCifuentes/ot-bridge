"""Prueba de humo de extremo a extremo del stack IT (no modifica la capa OT ni escribe en el PLC).

Comprueba:
  1. Los 10 servicios de compose en marcha y healthy.
  2. Flujo PLC -> gateway -> MQTT -> historian -> InfluxDB (ultimo punto reciente) y la API (sensores al dia).
  3. Controles de seguridad: InfluxDB sin credenciales 401; API sin clave 401, clave de lectura GET 200 /
     POST 403; errores de cliente 4xx; Swagger deshabilitado.
  4. Alarma de prueba ACTIVE -> RESOLVED: activa un umbral siempre verdadero ("PRUEBA DE HUMO"), espera la alarma
     en la API y lo desactiva (el motor resuelve las alarmas de reglas retiradas). Reutiliza siempre el mismo
     umbral. Tarda ~1 min; se omite con --quick. La alarma se ve tambien en el SCADA (severidad warning).

Uso:  .\\venv\\Scripts\\python.exe scripts\\smoke_test.py [--quick]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8080"
INFLUX = "http://127.0.0.1:8086"
SERVICES = {"mosquitto", "influxdb", "historian", "grafana", "postgres", "plant-api", "alarm-engine", "gateway",
            "opcua-server", "digital-twin"}
SMOKE_MESSAGE = "PRUEBA DE HUMO (smoke test)"
MAX_AGE_S = 15

results: list[tuple[bool, str, str]] = []


def env() -> dict[str, str]:
    out = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def check(ok: bool, name: str, detail: str = "") -> bool:
    results.append((ok, name, detail))
    print(f"  [{'OK ' if ok else 'ERR'}] {name}{'  ' + detail if detail else ''}")
    return ok


def http(url: str, method: str = "GET", headers: dict | None = None, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, str(exc)


def influx_query(q: str, user: str | None = None, password: str | None = None) -> tuple[int, object]:
    headers = {}
    if user:
        headers["Authorization"] = "Basic " + b64encode(f"{user}:{password}".encode()).decode()
    url = f"{INFLUX}/query?" + urllib.parse.urlencode({"db": "plant", "q": q, "epoch": "s"})
    return http(url, headers=headers)


def services() -> None:
    print("\n== Servicios")
    out = subprocess.run(["docker", "compose", "ps", "--format", "json"], cwd=ROOT, capture_output=True, text=True)
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip().startswith("{")]
    state = {r["Service"]: (r.get("State"), r.get("Health")) for r in rows}
    for name in sorted(SERVICES):
        st, health = state.get(name, ("ausente", ""))
        check(st == "running" and health == "healthy", f"{name}", f"{st} {health}".strip())


def data_flow(e: dict[str, str], key: str) -> None:
    print("\n== Flujo de datos")
    code, body = influx_query('SELECT last("value") FROM "sensor_readings" WHERE "variable" = \'nivel_x10\'',
                              e["INFLUX_READ_USER"], e["INFLUX_READ_PASSWORD"])
    try:
        ts = body["results"][0]["series"][0]["values"][0][0]
        age = time.time() - ts
        check(age < MAX_AGE_S, "InfluxDB recibe telemetria", f"ultimo punto hace {age:.0f} s")
    except (TypeError, KeyError, IndexError):
        check(False, "InfluxDB recibe telemetria", f"HTTP {code}")
    code, machines = http(f"{API}/api/machines", headers={"X-API-Key": key})
    online = code == 200 and any(m["name"] == "plc01" and m["online"] for m in items(machines))
    check(online, "API: plc01 online", f"HTTP {code}")
    code, sensors = http(f"{API}/api/sensors", headers={"X-API-Key": key})
    if code == 200:
        stamps = [s["lastTs"] for s in items(sensors) if s.get("lastTs")]
        newest = max(stamps) if stamps else None
        age = time.time() - _iso(newest) if newest else None
        check(age is not None and age < MAX_AGE_S, "API consume MQTT (sensores al dia)",
              f"ultimo hace {age:.0f} s" if age is not None else "sin datos")
    else:
        check(False, "API consume MQTT (sensores al dia)", f"HTTP {code}")


def items(body) -> list:
    """Listas planas o respuestas paginadas ({"content": [...]})."""
    if isinstance(body, dict):
        return body.get("content", [])
    return body if isinstance(body, list) else []


def _iso(value: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def security(e: dict[str, str]) -> None:
    print("\n== Seguridad y errores")
    read, op = e["API_KEY_GRAFANA"], e["API_KEY_OPERATOR"]
    check(influx_query("SHOW DATABASES")[0] == 401, "InfluxDB sin credenciales -> 401")
    check(http(f"{API}/actuator/health")[0] == 200, "API /actuator/health -> 200 (sin clave)")
    check(http(f"{API}/api/alarms")[0] == 401, "API sin clave -> 401")
    check(http(f"{API}/api/alarms", headers={"X-API-Key": "invalida"})[0] == 401, "API clave invalida -> 401")
    check(http(f"{API}/api/alarms", headers={"X-API-Key": read})[0] == 200, "API clave lectura GET -> 200")
    check(http(f"{API}/api/thresholds", "POST", {"X-API-Key": read}, {})[0] == 403, "API clave lectura POST -> 403")
    check(http(f"{API}/api/nope", headers={"X-API-Key": read})[0] == 404, "Ruta inexistente -> 404")
    check(http(f"{API}/api/alarms?state=FOO", headers={"X-API-Key": read})[0] == 400, "Enum invalido -> 400")
    check(http(f"{API}/api/thresholds", "POST", {"X-API-Key": op}, {"variable": "x"})[0] == 400,
          "Validacion -> 400")
    check(http(f"{API}/swagger-ui/index.html")[0] == 404, "Swagger deshabilitado (prod) -> 404")


def alarm_roundtrip(e: dict[str, str]) -> None:
    print("\n== Alarma de prueba ACTIVE -> RESOLVED (hasta ~90 s)")
    read, op = {"X-API-Key": e["API_KEY_GRAFANA"]}, {"X-API-Key": e["API_KEY_OPERATOR"]}
    body = {"variable": "nivel_x10", "operator": "ge", "value": -32768, "severity": "warning",
            "message": SMOKE_MESSAGE, "enabled": True, "deadband": 0, "delaySeconds": 0}
    _, thresholds = http(f"{API}/api/thresholds", headers=read)
    existing = next((t for t in items(thresholds) if t["message"] == SMOKE_MESSAGE), None)
    if existing:
        code, threshold = http(f"{API}/api/thresholds/{existing['id']}", "PUT", op, body)
    else:
        code, threshold = http(f"{API}/api/thresholds", "POST", op, body)
    if not check(code in (200, 201) and threshold, "Umbral de prueba activado", f"HTTP {code}"):
        return
    alarm_code = f"th{threshold['id']}"
    try:
        alarm = _wait_alarm(read, alarm_code, {"ACTIVE", "ACKNOWLEDGED"}, 70)
        check(alarm is not None, "Alarma ACTIVE en la API", alarm_code)
    finally:
        body["enabled"] = False
        code, _ = http(f"{API}/api/thresholds/{threshold['id']}", "PUT", op, body)
        check(code == 200, "Umbral de prueba desactivado", f"HTTP {code}")
    if alarm:
        resolved = _wait_alarm(read, alarm_code, {"RESOLVED"}, 70, alarm_id=alarm["id"])
        check(resolved is not None, "Alarma RESOLVED al retirar la regla", alarm_code)


def _wait_alarm(headers: dict, code: str, states: set[str], timeout_s: int, alarm_id: int | None = None):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, page = http(f"{API}/api/alarms?size=50", headers=headers)
        for a in (page or {}).get("content", []) if status == 200 else []:
            if a.get("code") == code and a["state"] in states and (alarm_id is None or a["id"] == alarm_id):
                return a
        time.sleep(3)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="omite la alarma de prueba")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    e = env()
    services()
    data_flow(e, e["API_KEY_GRAFANA"])
    security(e)
    if not args.quick:
        alarm_roundtrip(e)
    failed = [name for ok, name, _ in results if not ok]
    print(f"\nRESULTADO: {len(results) - len(failed)}/{len(results)} OK" + (f"  FALLOS: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
