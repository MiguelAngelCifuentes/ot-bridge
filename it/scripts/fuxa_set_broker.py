"""Cambia solo la direccion del broker MQTT (dispositivo IT-Broker) de un proyecto FUXA, con backup previo.

No toca vistas, scripts, alarmas ni el resto de dispositivos: la pestana "Simulador" de la planta se conserva.
Idempotente: si la direccion ya es la pedida, no escribe nada. Las credenciales MQTT (usuario fuxa,
MQTT_PASSWORD_FUXA de .env) se reaplican al almacen de seguridad de FUXA, nunca dentro del proyecto.

Uso:  python scripts/fuxa_set_broker.py --fuxa http://localhost:1881 --broker mqtt://mosquitto:1883
      (un solo host: FUXA y mosquitto comparten la red Docker fuxa_default)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HMI = ROOT.parent / "ot" / "scada" / "hmi"
sys.path.insert(0, str(HMI))
from deploy import call, env, login  # noqa: E402

DEVICE_ID = "d_mqtt_it"
DEVICE_NAME = "IT-Broker"


def find_device(project: dict) -> dict | None:
    devices = project.get("devices") or {}
    return devices.get(DEVICE_ID) or next((d for d in devices.values() if d.get("name") == DEVICE_NAME), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fuxa", default="http://localhost:1881", help="URL de FUXA")
    parser.add_argument("--broker", required=True, help="p. ej. mqtt://mosquitto:1883")
    parser.add_argument("--client-id", default="fuxa-scada-plant")
    args = parser.parse_args()

    try:
        token = login(args.fuxa)
        project = call(f"{args.fuxa}/api/project", token=token)
    except (urllib.error.URLError, OSError) as exc:
        print(f"ERROR: FUXA no responde en {args.fuxa} ({exc})", file=sys.stderr)
        return 1

    device = find_device(project)
    if device is None:
        print(f"ERROR: el proyecto FUXA no tiene el dispositivo {DEVICE_NAME} ({DEVICE_ID})", file=sys.stderr)
        return 1
    current = (device.get("property") or {}).get("address")
    if current == args.broker:
        print(f"{DEVICE_NAME} ya apunta a {args.broker}: sin cambios")
        return 0

    backup_dir = HMI / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"broker-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    backup.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    print(f"backup: {backup}")

    device.setdefault("property", {})["address"] = args.broker
    try:
        call(f"{args.fuxa}/api/project", "POST", project, token)
        security = {"clientId": args.client_id, "uid": "fuxa", "pwd": env("MQTT_PASSWORD_FUXA")}
        call(f"{args.fuxa}/api/device", "POST", {"params": {"query": "security", "name": device["id"],
                                                             "value": security}}, token)
    except urllib.error.HTTPError as exc:
        print(f"ERROR {exc.code}: {exc.read().decode()[:300]} (restaurar: python ot/scada/hmi/deploy.py --target plant --rollback {backup})",
              file=sys.stderr)
        return 1

    check = find_device(call(f"{args.fuxa}/api/project", token=token))
    applied = (check.get("property") or {}).get("address") if check else None
    if applied != args.broker:
        print(f"ERROR: tras guardar, {DEVICE_NAME} apunta a {applied}", file=sys.stderr)
        return 1
    print(f"{DEVICE_NAME}: {current} -> {args.broker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
