"""Pruebas funcionales del SCADA en el sandbox: se pulsan los botones reales del HMI (Playwright) y se
comprueba en el simulador del PLC (Modbus 127.0.0.1:5502) que la logica responde como el programa .st.

Solo contra el sandbox: nunca contra la planta ni el PLC real.
Uso:  python ot/scada/hmi/sandbox/test_hmi.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from pymodbus.client import ModbusTcpClient

BASE = "http://127.0.0.1:1882"
HR = {"nivel": 1124, "estado": 1129, "modo": 1130, "marcha": 1131, "valvula": 1132, "reset": 1133,
      "consigna": 1134, "seta_scada": 1135, "sim_no_confirm": 2000, "sim_sensor_fail": 2001}
BIT = {"contactor": 1, "seta": 2, "fallo_sensor": 4, "fallo_arranque": 8, "manual": 128, "orden_bomba": 256}

results: list[tuple[str, bool, str]] = []


class Plc:
    def __init__(self) -> None:
        self.c = ModbusTcpClient("127.0.0.1", port=5502)
        self.c.connect()

    def get(self, name: str) -> int:
        return self.c.read_holding_registers(HR[name], count=1, device_id=1).registers[0]

    def set(self, name: str, value: int) -> None:
        self.c.write_register(HR[name], value, device_id=1)

    def bit(self, name: str) -> bool:
        return bool(self.get("estado") & BIT[name])


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'OK ' if ok else 'FALLO'}] {name} {detail}")


def wait_for(cond, timeout=8.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.3)
    return False


def click(page: Page, label: str) -> None:
    page.get_by_role("button", name=label, exact=True).locator("visible=true").first.click()
    page.wait_for_timeout(700)


def visible(page: Page, label: str) -> bool:
    return page.get_by_role("button", name=label, exact=True).locator("visible=true").count() > 0


def supervisor_profile() -> dict | None:
    settings = json.load(urllib.request.urlopen(f"{BASE}/api/settings"))
    if not settings.get("secureEnabled"):
        return None
    root = Path(__file__).resolve().parents[4] / "it"
    pwd = [l.split("=", 1)[1].strip() for l in (root / ".env").read_text(encoding="utf-8").splitlines()
           if l.startswith("FUXA_SUPERVISOR_PASSWORD=")][0]
    req = urllib.request.Request(f"{BASE}/api/signin", json.dumps({"username": "supervisor", "password": pwd}).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))["data"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", type=Path, default=Path(__file__).resolve().parent.parent / "build" / "tests")
    args = parser.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    plc = Plc()
    # estado inicial conocido
    for n, v in (("seta_scada", 0), ("sim_no_confirm", 0), ("sim_sensor_fail", 0), ("modo", 0)):
        plc.set(n, v)
    time.sleep(0.5)
    plc.set("reset", 1)          # un fallo de arranque enclavado de una ejecucion previa bloquearia la marcha
    time.sleep(1.5)

    with sync_playwright() as p:
        ctx = p.chromium.launch().new_context(viewport={"width": 1600, "height": 900})
        profile = supervisor_profile()
        if profile:     # con la seguridad activa, las pruebas operan como supervisor
            ctx.add_init_script(f"sessionStorage.setItem('currentUser', {json.dumps(json.dumps(profile))});")
        page = ctx.new_page()
        page.goto(f"{BASE}/view?name=Mando", wait_until="networkidle")
        page.wait_for_timeout(4000)

        print("1. Modo AUTOMATICO: mandos manuales ocultos")
        check("MARCHA oculta en AUTO", not visible(page, "MARCHA"))
        check("ABRIR oculta en AUTO", not visible(page, "ABRIR"))

        print("2. Paso a MANUAL con confirmacion (arranque sin salto)")
        estaba_marcha = plc.bit("orden_bomba")
        click(page, "MANUAL")
        check("dialogo de confirmacion abierto", visible(page, "PASAR A MANUAL"))
        check("sin confirmar no cambia el modo", plc.get("modo") == 0)
        click(page, "PASAR A MANUAL")
        check("modo = MANUAL en el PLC", wait_for(lambda: plc.bit("manual")))
        check("consigna sembrada al 75 %", wait_for(lambda: plc.get("consigna") == 75), f"({plc.get('consigna')})")
        check("la bomba conserva su estado", plc.bit("orden_bomba") == estaba_marcha)
        page.wait_for_timeout(2500)
        check("MARCHA visible en MANUAL", visible(page, "MARCHA"))
        page.screenshot(path=str(args.shots / "01-manual.png"))

        print("3. PARO inmediato y MARCHA con confirmacion")
        click(page, "PARO")
        check("PARO sin confirmacion", wait_for(lambda: not plc.bit("orden_bomba")))
        click(page, "MARCHA")
        check("dialogo de marcha abierto", visible(page, "ARRANCAR"))
        click(page, "ARRANCAR")
        check("orden de marcha dada", wait_for(lambda: plc.bit("orden_bomba")))
        check("contactor confirma", wait_for(lambda: plc.bit("contactor")))

        print("4. Fallo de arranque (el contactor no confirma)")
        click(page, "PARO")
        wait_for(lambda: not plc.bit("contactor"))
        plc.set("sim_no_confirm", 1)
        click(page, "MARCHA")
        click(page, "ARRANCAR")
        check("fallo de arranque a los 3 s", wait_for(lambda: plc.bit("fallo_arranque"), 6))
        page.wait_for_timeout(2500)
        check("RESET visible con el fallo", visible(page, "RESET FALLOS"))
        page.screenshot(path=str(args.shots / "02-fallo-arranque.png"))
        plc.set("sim_no_confirm", 0)
        click(page, "RESET FALLOS")
        click(page, "RESET")
        check("reset por pulso limpia el fallo", wait_for(lambda: not plc.bit("fallo_arranque")))
        check("registro de reset vuelve a 0", plc.get("reset") == 0)
        page.wait_for_timeout(2500)
        check("RESET oculto sin fallo", not visible(page, "RESET FALLOS"))

        print("5. Paro de emergencia SCADA")
        click(page, "PARO DE EMERGENCIA")
        check("seta SCADA activa al instante", wait_for(lambda: plc.get("seta_scada") == 1, 3))
        check("seta anula la orden de marcha", wait_for(lambda: not plc.bit("orden_bomba")))
        page.wait_for_timeout(2500)
        check("REARMAR visible", visible(page, "REARMAR SETA SCADA"))
        page.screenshot(path=str(args.shots / "03-seta-scada.png"))
        click(page, "REARMAR SETA SCADA")
        click(page, "REARMAR")
        check("rearme con confirmacion", wait_for(lambda: plc.get("seta_scada") == 0))

        print("6. Fallo del transmisor LT-101")
        plc.set("sim_sensor_fail", 1)
        check("bit fallo sensor", wait_for(lambda: plc.bit("fallo_sensor")))
        page.goto(f"{BASE}/view?name=Alarmas", wait_until="networkidle")
        page.wait_for_timeout(7000)
        body = page.inner_text("body")
        check("alarma FALLO LT-101 en la tabla", "FALLO TRANSMISOR" in body)
        page.screenshot(path=str(args.shots / "04-alarma-sensor.png"))
        plc.set("sim_sensor_fail", 0)

        print("7. Vuelta a AUTOMATICO")
        page.goto(f"{BASE}/view?name=Mando", wait_until="networkidle")
        page.wait_for_timeout(3000)
        click(page, "AUTOMÁTICO")
        check("modo = AUTO", wait_for(lambda: not plc.bit("manual")))

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} comprobaciones OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
