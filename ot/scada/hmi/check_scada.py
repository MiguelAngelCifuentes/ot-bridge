"""Comprueba que el SCADA recibe datos en vivo del PLC (PLC_Tanque) y del simulador (SIM_Campo).

Uso:  python ot/scada/hmi/check_scada.py --target plant|sandbox [--timeout 120]
Sale con 0 si todos los dispositivos Modbus entregan valores; 1 en caso contrario.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import URLS, call, login  # noqa: E402

DEVICES = ("PLC_Tanque", "SIM_Campo")


def sample_tags(project: dict) -> dict[str, list[str]]:
    tags = {}
    for device in (project.get("devices") or {}).values():
        if device.get("name") in DEVICES:
            tags[device["name"]] = list((device.get("tags") or {}).keys())[:3]
    return tags


def values(base: str, token: str | None, ids: list[str]) -> list:
    query = urllib.parse.urlencode({"ids": json.dumps(ids)})
    result = call(f"{base}/api/getTagValue?{query}", token=token) or []
    return [r.get("value") for r in result if isinstance(r, dict)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=URLS, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    base = URLS[args.target]
    token = login(base)
    tags = sample_tags(call(f"{base}/api/project", token=token))
    missing = [d for d in DEVICES if d not in tags]
    if missing:
        print(f"ERROR: el proyecto FUXA no tiene los dispositivos {missing}", file=sys.stderr)
        return 1

    pending = set(DEVICES)
    deadline = time.time() + args.timeout
    while pending and time.time() < deadline:
        for device in list(pending):
            if any(v not in (None, "") for v in values(base, token, tags[device])):
                print(f"{device}: datos en vivo")
                pending.discard(device)
        if pending:
            time.sleep(5)
    if pending:
        print(f"ERROR: sin datos de {sorted(pending)} (plugin modbus-serial instalado? PLC en RUN?)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
