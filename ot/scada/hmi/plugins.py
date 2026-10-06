"""Instala en FUXA el plugin de comunicaciones Modbus (modbus-serial) si falta. Idempotente.

FUXA no incluye el driver Modbus de serie: sin el, los dispositivos PLC_Tanque y SIM_Campo no conectan.
El plugin se descarga con npm dentro del contenedor y queda persistido en el volumen fuxa-pkg.

Uso:  python ot/scada/hmi/plugins.py --target plant|sandbox
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import URLS, call, login  # noqa: E402

REQUIRED = "modbus-serial"


def installed(base: str, token: str | None) -> dict | None:
    for plugin in call(f"{base}/api/plugins", token=token) or []:
        if plugin.get("name") == REQUIRED:
            return plugin
    raise SystemExit(f"FUXA no ofrece el plugin {REQUIRED}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=URLS, required=True)
    args = parser.parse_args()
    base = URLS[args.target]
    token = login(base)

    plugin = installed(base, token)
    if plugin.get("current"):
        print(f"{REQUIRED} ya instalado ({plugin['current']})")
        return 0
    print(f"instalando {REQUIRED} {plugin.get('version', '')} (npm, puede tardar 1 min)...")
    try:
        call(f"{base}/api/plugins", "POST", {"params": plugin}, token)
    except urllib.error.HTTPError as exc:
        print(f"ERROR {exc.code}: {exc.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1
    deadline = time.time() + 300
    while time.time() < deadline:
        current = installed(base, token).get("current")
        if current:
            print(f"{REQUIRED} instalado ({current})")
            return 0
        time.sleep(5)
    print(f"ERROR: {REQUIRED} no aparece instalado tras 5 min", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
