"""Pruebas de permisos por rol en el sandbox (FUXA con seguridad activa).

Para cada usuario (invitado, visitante, operador, supervisor) comprueba en la vista Mando:
- PARO DE EMERGENCIA: deshabilitado para invitado y visitante (FUXA lo muestra sin eventos y el servidor
  rechaza escrituras de invitado), operable para operador/supervisor.
- REARMAR SETA SCADA (con la seta activa): solo visible para supervisor.
- Navegacion Diagnostico: solo supervisor.
Uso:  python ot/scada/hmi/sandbox/test_roles.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy import call, env  # noqa: E402
from test_hmi import BASE, Plc  # noqa: E402

USERS = {"invitado": None, "visitante": "FUXA_VISITANTE_PASSWORD", "operador": "FUXA_OPERADOR_PASSWORD",
         "supervisor": "FUXA_SUPERVISOR_PASSWORD"}
# (paro visible, paro habilitado, rearme visible, diagnostico en navegacion)
EXPECTED = {"invitado": (True, False, False, False), "visitante": (True, False, False, False),
            "operador": (True, True, False, False), "supervisor": (True, True, True, True)}


def button_state(page, label: str) -> tuple[bool, bool]:
    btn = page.get_by_role("button", name=label, exact=True)
    if btn.count() == 0 or not btn.first.is_visible():
        return False, False
    return True, btn.first.is_enabled()


def main() -> int:
    plc = Plc()
    plc.set("seta_scada", 1)             # con la seta SCADA activa el boton de rearme debe aparecer
    time.sleep(1.5)
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for user, key in USERS.items():
            profile = None
            if key:
                profile = call(f"{BASE}/api/signin", "POST", {"username": user, "password": env(key)})["data"]
            ctx = browser.new_context(viewport={"width": 1600, "height": 900})
            if profile:
                ctx.add_init_script(f"sessionStorage.setItem('currentUser', {json.dumps(json.dumps(profile))});")
            page = ctx.new_page()
            page.goto(f"{BASE}/view?name=Mando", wait_until="networkidle")
            page.wait_for_timeout(4500)
            paro_vis, paro_en = button_state(page, "PARO DE EMERGENCIA")
            rearme_vis, _ = button_state(page, "REARMAR SETA SCADA")
            token = profile["token"] if profile else None
            nav = [i["text"] for i in call(f"{BASE}/api/project", token=token)["hmi"]["layout"]["navigation"]["items"]]
            got = (paro_vis, paro_en, rearme_vis, "Diagnóstico" in nav)
            ok = got == EXPECTED[user]
            failures += not ok
            print(f"  [{'OK ' if ok else 'FALLO'}] {user:<10} paro visible={got[0]} habilitado={got[1]} "
                  f"rearme={got[2]} diagnostico={got[3]}")
            ctx.close()
        browser.close()
    plc.set("seta_scada", 0)
    print(f"\n{len(USERS) - failures}/{len(USERS)} roles correctos")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
