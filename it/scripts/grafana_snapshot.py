"""Capturas de la suite de dashboards de Grafana con Chromium headless (docs/images y revision visual).

Uso:  .\\venv\\Scripts\\python.exe scripts\\grafana_snapshot.py [--out DIR] [--uids otb-home,otb-process]
Inicia sesion como admin (GRAFANA_PASSWORD de .env) y guarda grafana-<uid>.png en modo kiosk.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
GRAFANA = "http://127.0.0.1:3000"
UIDS = ["otb-home", "otb-process", "otb-alarms", "otb-twin", "otb-maintenance", "otb-explorer", "otb-system"]


def grafana_password() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GRAFANA_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Falta GRAFANA_PASSWORD en .env")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT.parent / "docs" / "images")
    parser.add_argument("--uids", default=",".join(UIDS))
    parser.add_argument("--wait", type=int, default=9000, help="ms de espera para que carguen los paneles")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1700, "height": 1000})
        page.goto(f"{GRAFANA}/login")
        page.fill("input[name=user]", "admin")
        page.fill("input[name=password]", grafana_password())
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
        for uid in args.uids.split(","):
            page.goto(f"{GRAFANA}/d/{uid}?kiosk")
            page.wait_for_timeout(args.wait)
            path = args.out / f"grafana-{uid.removeprefix('otb-')}.png"
            page.screenshot(path=str(path))
            print(path)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
