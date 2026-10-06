"""V4 · Mando y seguridades: modo, bomba, valvula, seguridades y paro de emergencia SCADA.

Reglas (del programa PLC):
- Los mandos de bomba y valvula solo actuan en MANUAL; se muestran solo con `mando_habilitado`.
- Cualquier seguridad (seta, fallo sensor, fallo arranque) anula la orden de marcha en el PLC.
- Pasar a MANUAL, dar MARCHA y RESET piden confirmacion; PARO y el paro SCADA actuan al instante.
- El rearme de la seta SCADA es solo para supervisor.
"""
from __future__ import annotations

from lib import (CRIT, EMERG, EQUIP_DARK, MANUAL, OPERATE, PANEL_EDGE, PROCESS, RUN, SUPERVISE, TEXT,
                 TEXT_DIM, WARN, View, act, alarm_table, button, card, ev_dialog, ev_set, lamp, number_input, perm,
                 rect, slider, text, value)
from model import T
from views.common import PUMP_RANGES, VIEW_IDS, status_bar

P_OP = perm(enable=OPERATE)
P_SUP = perm(show=SUPERVISE, enable=SUPERVISE)
ONLY_MANUAL = [act("hide", T["mando_habilitado"], 0, 0), act("show", T["mando_habilitado"], 1, 1)]


def build() -> View:
    v = View(VIEW_IDS["control"], "Mando")
    status_bar(v, "MANDO Y SEGURIDADES")

    # ---------------------------------------------------------------- modo
    card(v, 24, 84, 380, 330, "Modo de operación")
    value(v, "ct_modo", T["txt_modo"], 214, 170, size=34, weight="bold")
    button(v, "ct_auto", "AUTOMÁTICO", 44, 200, 164, 64, tag=T["CMD_modo"], events=[ev_set(0)], permission=P_OP,
           ranges=[(0, 0, RUN, "#FFFFFF"), (1, 1, EQUIP_DARK, TEXT)])
    button(v, "ct_manual", "MANUAL", 220, 200, 164, 64, tag=T["CMD_modo"],
           events=[ev_dialog(VIEW_IDS["dlg_manual"])], permission=P_OP,
           ranges=[(0, 0, EQUIP_DARK, TEXT), (1, 1, MANUAL, "#FFFFFF")])
    v.static(text(44, 300, "Al pasar a MANUAL el PLC conserva el estado", 13, TEXT_DIM))
    v.static(text(44, 320, "de la bomba y fija la consigna al 75 % (sin salto).", 13, TEXT_DIM))
    v.static(text(44, 356, "En AUTOMÁTICO el PLC gobierna la bomba por", 13, TEXT_DIM))
    v.static(text(44, 376, "nivel (300 → 900 L) y el consumo por reserva.", 13, TEXT_DIM))

    # ---------------------------------------------------------------- bomba
    card(v, 424, 84, 600, 330, "Bomba P-101 · llenado", "mandos solo en MANUAL")
    lamp(v, "ct_p101", T["estado_bomba"], 444, 124, 36, 36, shape="circle", ranges=PUMP_RANGES,
         blink=(0, 3, 3, "#FF9830", "#6B4A1F"))
    value(v, "ct_p101_txt", T["txt_bomba"], 494, 150, size=20, anchor="start", weight="bold")
    v.static(text(760, 136, "VELOCIDAD", 11, TEXT_DIM, extra='letter-spacing="1"'))
    value(v, "ct_vel", T["P101_velocidad"], 760, 164, size=26, color=PROCESS, unit="%", digits=0, anchor="start")
    v.static(text(890, 136, "CONSIGNA", 11, TEXT_DIM, extra='letter-spacing="1"'))
    value(v, "ct_cons", T["CMD_consigna"], 890, 164, size=26, color=WARN, unit="%", digits=0, anchor="start")
    button(v, "ct_marcha", "MARCHA", 444, 190, 170, 64, tag=T["CMD_marcha"],
           events=[ev_dialog(VIEW_IDS["dlg_marcha"])], permission=P_OP, bg="#2E7D32", fg="#FFFFFF",
           actions=ONLY_MANUAL)
    button(v, "ct_paro", "PARO", 626, 190, 170, 64, tag=T["CMD_marcha"], events=[ev_set(0)], permission=P_OP,
           bg="#5A6270", fg="#FFFFFF", actions=ONLY_MANUAL)
    v.static(text(444, 290, "CONSIGNA DE VELOCIDAD (0–100 %)", 11, TEXT_DIM, extra='letter-spacing="1"'))
    slider(v, "ct_cons_slider", T["CMD_consigna"], 434, 296, 420, 90, vmin=0, vmax=100, step=5, permission=P_OP)
    number_input(v, "ct_cons_input", T["CMD_consigna"], 874, 312, 130, 44, vmin=0, vmax=100, permission=P_OP,
                 actions=ONLY_MANUAL)
    v.static(text(939, 380, "campo: Enter aplica", 11, TEXT_DIM, "middle"))

    # ---------------------------------------------------------------- valvula
    card(v, 1044, 84, 532, 330, "Válvula V-101 · consumo", "mandos solo en MANUAL")
    lamp(v, "ct_v101", T["estado_valvula"], 1064, 124, 36, 36, shape="circle",
         ranges=[(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN)])
    value(v, "ct_v101_txt", T["txt_valvula"], 1114, 150, size=20, anchor="start", weight="bold")
    button(v, "ct_abrir", "ABRIR", 1064, 190, 230, 64, tag=T["CMD_valvula"], events=[ev_set(1)], permission=P_OP,
           bg="#1F4E79", fg="#FFFFFF", actions=ONLY_MANUAL)
    button(v, "ct_cerrar", "CERRAR", 1306, 190, 230, 64, tag=T["CMD_valvula"], events=[ev_set(0)],
           permission=P_OP, bg="#5A6270", fg="#FFFFFF", actions=ONLY_MANUAL)
    v.static(text(1064, 300, "Consumo:", 14, TEXT_DIM))
    value(v, "ct_consumo", T["txt_consumo"], 1134, 300, size=14, anchor="start", weight="bold")
    v.static(text(1064, 336, "En AUTOMÁTICO el PLC cierra el consumo en reserva", 13, TEXT_DIM))
    v.static(text(1064, 356, "(≤ 200 L) y lo reabre con ≥ 250 L. La seta cierra", 13, TEXT_DIM))
    v.static(text(1064, 376, "la válvula en cualquier modo.", 13, TEXT_DIM))

    # ---------------------------------------------------------------- seguridades
    card(v, 24, 434, 560, 442, "Seguridades (seguridades_ok)")
    value(v, "ct_seg_txt", T["txt_seguridades"], 304, 500, size=24, weight="bold")
    for i, (bit, tagname, label, desc) in enumerate(((2, "b_seta", "Seta de emergencia", "física o SCADA (MW111)"),
                                                     (4, "b_fsensor", "Fallo transmisor LT-101",
                                                      "señal fuera de 3,5–20,5 mA"),
                                                     (8, "b_farranque", "Fallo de arranque P-101",
                                                      "orden ≠ confirmación durante 3 s"))):
        y = 530 + i * 76
        v.static(rect(44, y, 520, 64, "#2E343D", PANEL_EDGE, 6))
        lamp(v, f"ct_seg_{bit}", T[tagname], 60, y + 16, 32, 32, shape="circle", ranges=[(0, 0, RUN), (1, 1, CRIT)])
        v.static(text(108, y + 28, label, 16, TEXT, weight="bold"))
        v.static(text(108, y + 50, desc, 12, TEXT_DIM))
    button(v, "ct_reset", "RESET FALLOS", 44, 766, 520, 60, tag=T["CMD_reset"],
           events=[ev_dialog(VIEW_IDS["dlg_reset"])], permission=P_OP, bg=WARN, fg="#1B1B1B",
           actions=[act("hide", T["reset_visible"], 0, 0), act("show", T["reset_visible"], 1, 1)])
    v.static(text(304, 852, "RESET visible solo con fallo de arranque y sin seta activa", 12, TEXT_DIM, "middle"))

    # ---------------------------------------------------------------- paro SCADA
    card(v, 604, 434, 420, 442, "Paro de emergencia SCADA")
    button(v, "ct_estop", "PARO DE EMERGENCIA", 634, 480, 360, 150, tag=T["CMD_seta_scada"], events=[ev_set(1)],
           permission=P_OP, bg=EMERG, fg="#FFFFFF", size=24)
    v.static(text(814, 662, "PARO SOFTWARE · no sustituye a la seta física", 13, WARN, "middle", "bold"))
    v.static(text(814, 684, "Actúa al instante, sin confirmación.", 13, TEXT_DIM, "middle"))
    lamp(v, "ct_estop_lamp", T["CMD_seta_scada"], 634, 704, 360, 44, ranges=[(0, 0, "#2E343D"), (1, 1, EMERG)],
         blink=(0, 1, 1, EMERG, "#5A1A22"))
    v.static(text(814, 732, "SETA SCADA (MW111)", 14, "#FFFFFF", "middle", "bold", extra='pointer-events="none"'))
    button(v, "ct_rearme", "REARMAR SETA SCADA", 634, 766, 360, 60, tag=T["CMD_seta_scada"],
           events=[ev_dialog(VIEW_IDS["dlg_rearme"])], permission=P_SUP, bg="#5A6270", fg="#FFFFFF",
           actions=[act("hide", T["CMD_seta_scada"], 0, 0), act("show", T["CMD_seta_scada"], 1, 1)])
    v.static(text(814, 852, "Rearme reservado a supervisor", 12, TEXT_DIM, "middle"))

    # ---------------------------------------------------------------- alarmas
    card(v, 1044, 434, 532, 442, "Alarmas activas")
    alarm_table(v, "ct_alarms", 1060, 474, 500, 390, compact=True)
    return v
