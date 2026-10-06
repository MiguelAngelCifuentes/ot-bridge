"""Despliega el proyecto FUXA generado (o restaura un backup) con copia de seguridad previa.

Uso:
  python ot/scada/hmi/deploy.py --target sandbox                 # despliega build/project-sandbox.json
  python ot/scada/hmi/deploy.py --target plant                   # despliega build/project-plant.json en la planta
  python ot/scada/hmi/deploy.py --target plant --rollback <json> # restaura un backup
  python ot/scada/hmi/deploy.py --target plant --backup-only [--out DIR]   # solo copia (lectura), sin desplegar
La URL de FUXA de la planta se toma de FUXA_URL (por defecto http://127.0.0.1:1881).
Si FUXA tiene la seguridad activa, se autentica con FUXA_ADMIN_USER / FUXA_ADMIN_PASSWORD de .env.
Los backups (contienen secretos) van a ot/scada/hmi/backups/, fuera del control de versiones.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HMI = Path(__file__).resolve().parent
ROOT = HMI.parents[2] / "it"   # .env del stack
URLS = {"sandbox": "http://127.0.0.1:1882", "plant": os.environ.get("FUXA_URL", "http://127.0.0.1:1881")}


def env(name: str, default: str | None = None) -> str | None:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return default


def call(url: str, method: str = "GET", body=None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-access-token"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


def login(base: str) -> str | None:
    settings = call(f"{base}/api/settings")
    if not settings.get("secureEnabled"):
        return None
    user, pwd = env("FUXA_ADMIN_USER", "admin"), env("FUXA_ADMIN_PASSWORD")
    if not pwd:
        raise SystemExit("FUXA tiene seguridad activa: define FUXA_ADMIN_PASSWORD en .env")
    res = call(f"{base}/api/signin", "POST", {"username": user, "password": pwd})
    return res["data"]["token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=URLS, required=True)
    parser.add_argument("--rollback", type=Path, help="backup JSON a restaurar")
    parser.add_argument("--backup-only", action="store_true", help="solo descarga el proyecto (GET)")
    parser.add_argument("--out", type=Path, help="directorio del backup (por defecto ot/scada/hmi/backups)")
    args = parser.parse_args()
    base = URLS[args.target]
    token = login(base)

    backup_dir = args.out or HMI / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    current = call(f"{base}/api/project", token=token)
    backup = backup_dir / f"{args.target}-{stamp}.json"
    backup.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    print(f"backup: {backup}")
    if args.backup_only:
        return 0

    source = args.rollback or HMI / "build" / f"project-{args.target}.json"
    project = json.loads(source.read_text(encoding="utf-8"))
    try:
        call(f"{base}/api/project", "POST", project, token)
    except urllib.error.HTTPError as exc:
        print(f"ERROR {exc.code}: {exc.read().decode()[:300]}", file=sys.stderr)
        return 1
    # Credenciales del broker IT: al almacen de seguridad de FUXA, nunca dentro del proyecto
    security = {"clientId": f"fuxa-scada-{args.target}", "uid": "fuxa", "pwd": env("MQTT_PASSWORD_FUXA")}
    call(f"{base}/api/device", "POST", {"params": {"query": "security", "name": "d_mqtt_it",
                                                   "value": security}}, token)   # el servidor lo serializa
    check = call(f"{base}/api/project", token=token)
    leaked = [d["name"] for d in check["devices"].values() if (d.get("property") or {}).get("pwd")]
    if leaked:
        print(f"AVISO: dispositivos con contrasena dentro del proyecto: {leaked}", file=sys.stderr)
    views = [v["name"] for v in check["hmi"]["views"]]
    print(f"desplegado {source.name} en {args.target}: {len(views)} vistas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
