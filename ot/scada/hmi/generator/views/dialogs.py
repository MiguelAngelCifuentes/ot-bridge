"""Faceplates (detalle por equipo, nivel 3 ISA-101) y dialogos de confirmacion de mandos.

Los faceplates son la interaccion en dos pasos (abrir el equipo -> actuar), por eso sus mandos no
piden una segunda confirmacion; la vista Mando si la pide para MANUAL, MARCHA, RESET y rearme.
"""
from __future__ import annotations

from lib import (CRIT, EQUIP_DARK, MANUAL, OPERATE, PANEL, PANEL_EDGE, PROCESS, RUN, SUPERVISE, TEXT, TEXT_DIM,
                 WARN, View, act, button, ev_close, ev_set, lamp, perm, rect, text, value)
from model import T
from views.common import PUMP_RANGES, VIEW_IDS

P_OP = perm(enable=OPERATE)
P_SUP = perm(show=SUPERVISE, enable=SUPERVISE)
ONLY_MANUAL = [act("hide", T["mando_habilitado"], 0, 0), act("show", T["mando_habilitado"], 1, 1)]
W, H = 620, 440


def _frame(key: str, title: str, subtitle: str) -> View:
    v = View(VIEW_IDS[key], key, W, H, PANEL)
    v.static(rect(0, 0, W, 64, "#1E232A", "none", 0))
    v.static(text(24, 40, title, 20, TEXT, weight="bold"))
    v.static(text(W - 24, 40, subtitle, 13, TEXT_DIM, "end"))
    return v


def _row(v: View, name: str, y, label: str, tag: str, *, unit="", digits=None, color=TEXT):
    v.static(rect(24, y, W - 48, 44, "#2E343D", PANEL_EDGE, 6))
    v.static(text(40, y + 28, label, 14, TEXT_DIM))
    value(v, name, tag, W - 40, y + 29, size=17, color=color, unit=unit, digits=digits, anchor="end", weight="bold")


def _close(v: View) -> None:
    button(v, f"{v.id}_close", "CERRAR", W - 164, H - 64, 140, 48, events=[ev_close()], bg="#4A525D", size=14)


def faceplate_p101() -> View:
    v = _frame("dlg_p101", "P-101 · Bomba de llenado", "faceplate")
    lamp(v, "fp_p101", T["estado_bomba"], 24, 84, 40, 40, shape="circle", ranges=PUMP_RANGES,
         blink=(0, 3, 3, "#FF9830", "#6B4A1F"))
    value(v, "fp_p101_txt", T["txt_bomba"], 80, 112, size=22, anchor="start", weight="bold")
    # orden (bit 256) frente a confirmacion del contactor (bit 1)
    for x, bit, label in ((360, 256, "ORDEN PLC"), (480, 1, "CONTACTOR")):
        lamp(v, f"fp_p101_b{bit}", T["PLC_estado"], x, 88, 24, 24, shape="circle", bit=bit, on=RUN)
        v.static(text(x + 12, 128, label, 10, TEXT_DIM, "middle"))
    _row(v, "fp_p101_vel", 146, "Velocidad real", T["P101_velocidad"], unit="%", digits=0, color=PROCESS)
    _row(v, "fp_p101_cons", 196, "Consigna manual", T["CMD_consigna"], unit="%", digits=0, color=WARN)
    _row(v, "fp_p101_modo", 246, "Modo", T["txt_modo"])
    _row(v, "fp_p101_seg", 296, "Seguridades", T["txt_seguridades"])
    button(v, "fp_p101_marcha", "MARCHA", 24, H - 64, 170, 48, tag=T["CMD_marcha"], events=[ev_set(1)],
           permission=P_OP, bg="#2E7D32", fg="#FFFFFF", actions=ONLY_MANUAL)
    button(v, "fp_p101_paro", "PARO", 206, H - 64, 170, 48, tag=T["CMD_marcha"], events=[ev_set(0)],
           permission=P_OP, bg="#5A6270", fg="#FFFFFF", actions=ONLY_MANUAL)
    _close(v)
    return v


def faceplate_v101() -> View:
    v = _frame("dlg_v101", "V-101 · Válvula de consumo", "faceplate")
    lamp(v, "fp_v101", T["estado_valvula"], 24, 84, 40, 40, shape="circle",
         ranges=[(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN)])
    value(v, "fp_v101_txt", T["txt_valvula"], 80, 112, size=22, anchor="start", weight="bold")
    _row(v, "fp_v101_cons", 146, "Consumo", T["txt_consumo"])
    _row(v, "fp_v101_sal", 196, "Caudal de salida FT-102", T["FT102_caudal"], unit="l/min", digits=1, color=PROCESS)
    _row(v, "fp_v101_modo", 246, "Modo", T["txt_modo"])
    v.static(text(24, 326, "En AUTOMÁTICO el PLC abre el consumo salvo en reserva", 13, TEXT_DIM))
    v.static(text(24, 346, "(≤ 200 L, rearme ≥ 250 L), fallo de sensor o seta.", 13, TEXT_DIM))
    button(v, "fp_v101_abrir", "ABRIR", 24, H - 64, 170, 48, tag=T["CMD_valvula"], events=[ev_set(1)],
           permission=P_OP, bg="#1F4E79", fg="#FFFFFF", actions=ONLY_MANUAL)
    button(v, "fp_v101_cerrar", "CERRAR VÁLVULA", 206, H - 64, 190, 48, tag=T["CMD_valvula"], events=[ev_set(0)],
           permission=P_OP, bg="#5A6270", fg="#FFFFFF", actions=ONLY_MANUAL)
    _close(v)
    return v


def faceplate_lt101() -> View:
    v = _frame("dlg_lt101", "LT-101 · Transmisor de nivel", "faceplate")
    lamp(v, "fp_lt101", T["b_fsensor"], 24, 84, 40, 40, shape="circle", ranges=[(0, 0, RUN), (1, 1, CRIT)])
    value(v, "fp_lt101_txt", T["txt_sensor"], 80, 112, size=22, anchor="start", weight="bold")
    _row(v, "fp_lt101_nivel", 146, "Nivel calculado", T["LT101_nivel"], unit="L", digits=1, color=PROCESS)
    _row(v, "fp_lt101_ma", 196, "Señal 4–20 mA", T["LT101_ma"], unit="mA", digits=2, color=PROCESS)
    v.static(text(24, 280, "Rango válido: 3,50 – 20,50 mA (MA_MIN/MAX_VALIDO).", 13, TEXT_DIM))
    v.static(text(24, 302, "Nivel = (mA − 4) / 16 × 1000 L.", 13, TEXT_DIM))
    v.static(text(24, 334, "Con fallo de sensor el PLC detiene la bomba en", 13, WARN))
    v.static(text(24, 354, "automático, cierra el consumo y bloquea la marcha.", 13, WARN))
    _close(v)
    return v


def confirm(key: str, title: str, lines: list[str], tag: str, set_value: int, permission: int,
            color: str = "#2E7D32", label: str = "CONFIRMAR") -> View:
    v = View(VIEW_IDS[key], key, 560, 320, PANEL)
    v.static(rect(0, 0, 560, 64, "#1E232A", "none", 0))
    v.static(text(24, 40, title, 20, TEXT, weight="bold"))
    for i, ln in enumerate(lines):
        v.static(text(24, 110 + i * 26, ln, 15, TEXT if i == 0 else TEXT_DIM))
    button(v, f"{key}_ok", label, 24, 240, 250, 56, tag=tag, events=[ev_set(set_value), ev_close()],
           permission=permission, bg=color, fg="#FFFFFF")
    button(v, f"{key}_cancel", "CANCELAR", 286, 240, 250, 56, events=[ev_close()], bg="#4A525D")
    return v


def build() -> list[View]:
    return [
        faceplate_p101(), faceplate_v101(), faceplate_lt101(),
        confirm("dlg_manual", "Pasar a MANUAL", ["¿Pasar la planta a modo MANUAL?",
                                                 "El PLC conserva el estado de la bomba y fija",
                                                 "la consigna al 75 %. El ciclo automático queda",
                                                 "suspendido hasta volver a AUTOMÁTICO."],
                T["CMD_modo"], 1, P_OP, MANUAL, "PASAR A MANUAL"),
        confirm("dlg_marcha", "Marcha P-101", ["¿Arrancar la bomba P-101?",
                                               "Arrancará a la consigna manual actual.",
                                               "Las seguridades del PLC siguen activas."],
                T["CMD_marcha"], 1, P_OP, "#2E7D32", "ARRANCAR"),
        confirm("dlg_reset", "Reset de fallos", ["¿Rearmar el fallo de arranque?",
                                                  "Revise antes el contactor de P-101.",
                                                  "El PLC no rearma con la seta activa."],
                T["CMD_reset"], 1, P_OP, WARN, "RESET"),
        confirm("dlg_rearme", "Rearme seta SCADA", ["¿Rearmar el paro de emergencia SCADA?",
                                                     "Compruebe que la causa del paro está resuelta.",
                                                     "Acción reservada a supervisor."],
                T["CMD_seta_scada"], 0, P_SUP, "#5A6270", "REARMAR"),
    ]
