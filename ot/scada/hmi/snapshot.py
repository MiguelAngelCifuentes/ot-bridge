"""Capturas de las vistas del SCADA FUXA con Chromium headless (revision visual y docs/images).

Uso:  python ot/scada/hmi/snapshot.py [--target sandbox|plant] [--out DIR] [--views overview,process,...]
      [--user U --password P]   (si FUXA tiene la seguridad activa)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "generator"))

URLS = {"sandbox": "http://127.0.0.1:1882", "plant": os.environ.get("FUXA_URL", "http://127.0.0.1:1881")}
MAIN = ["overview", "process", "control", "alarms", "trends", "diagnostics"]
NAMES = {"overview": "Visión general", "process": "Proceso", "control": "Mando", "alarms": "Alarmas",
         "trends": "Tendencias", "diagnostics": "Diagnóstico", "simulation": "Simulador"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=URLS, default="sandbox")
    parser.add_argument("--out", type=Path, default=HERE / "build" / "snapshots")
    parser.add_argument("--views", default=",".join(MAIN))
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--wait", type=int, default=6000, help="ms de espera para que lleguen los datos")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    base = URLS[args.target]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(f"{base}/home", wait_until="networkidle")
        page.wait_for_timeout(3000)
        if args.user:
            page.locator("button:has(mat-icon:text('account_circle')), .header-login").first.click()
            page.fill("input[formcontrolname='username'], input[name='username']", args.user)
            page.fill("input[type='password']", args.password)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
        for key in args.views.split(","):
            page.goto(f"{base}/view?name={NAMES[key]}", wait_until="networkidle")   # vista sin cabecera
            page.wait_for_timeout(args.wait)
            path = args.out / f"fuxa-{key}.png"
            page.screenshot(path=str(path))
            print(path)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
