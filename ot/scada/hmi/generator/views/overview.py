"""V1 · Vision general: en 5 segundos, ¿esta bien la planta?"""
from __future__ import annotations

from lib import (CRIT, EQUIP_DARK, INFO, PANEL_EDGE, PROCESS, RUN, TEXT, TEXT_DIM, WARN, View, alarm_table,
                 card, ev_dialog, lamp, rect, text, value)
from model import T
from views.common import PUMP_RANGES, VIEW_IDS, kpi, status_bar, tank


def _equipment_row(v: View, name: str, y, tag_lamp: str, ranges, label: str, desc: str, tag_txt: str, dialog: str):
    x = 1136
    v.static(rect(x, y, 424, 72, "#2E343D", PANEL_EDGE, 6))
    lamp(v, f"{name}_lamp", tag_lamp, x + 16, y + 20, 32, 32, shape="circle", ranges=ranges,
         events=[ev_dialog(VIEW_IDS[dialog])] if dialog else None)
    v.static(text(x + 64, y + 30, label, 16, TEXT, weight="bold"))
    v.static(text(x + 64, y + 52, desc, 12, TEXT_DIM))
    value(v, f"{name}_txt", tag_txt, x + 408, y + 43, size=15, anchor="end", weight="bold")


def build() -> View:
    v = View(VIEW_IDS["overview"], "Visión general")
    status_bar(v, "VISIÓN GENERAL")

    # Deposito
    card(v, 24, 84, 380, 560, "Depósito TK-101", "0 – 1000 L")
    tank(v, "ov_tank", 90, 140, 160, 470)
    value(v, "ov_ma", T["LT101_ma"], 330, 628, size=13, color=TEXT_DIM, unit="mA (LT-101)", digits=2)

    # Indicadores de proceso
    kpi(v, "ov_ent", 424, 84, 220, 130, "Caudal entrada", T["FT101_caudal"], "l/min", 1, PROCESS)
    kpi(v, "ov_sal", 656, 84, 220, 130, "Caudal salida", T["FT102_caudal"], "l/min", 1, "#4FC3C3")
    kpi(v, "ov_bal", 888, 84, 220, 130, "Balance ent − sal", T["balance_lpm"], "l/min", 1, "#B877D9")
    kpi(v, "ov_vel", 424, 226, 220, 130, "Velocidad P-101", T["P101_velocidad"], "%", 0, PROCESS)
    kpi(v, "ov_cons", 656, 226, 220, 130, "Consigna manual", T["CMD_consigna"], "%", 0, WARN)
    kpi(v, "ov_nivel", 888, 226, 220, 130, "Nivel", T["LT101_nivel"], "L", 1, PROCESS)

    # Lectura rapida del ciclo automatico
    card(v, 424, 368, 684, 276, "Ciclo automático (programa PLC)")
    rows = [("Bomba P-101 arranca", "≤ 300 L", "y para en 900 L (lleno)"),
            ("Consumo V-101 se cierra", "≤ 200 L", "reserva; se reabre con ≥ 250 L"),
            ("Alarma nivel muy alto", "≥ 950 L", "bit 16 del registro de estado"),
            ("Alarma nivel muy bajo", "≤ 100 L", "bit 32 del registro de estado"),
            ("Fallo de arranque", "3 s", "orden y confirmación no coinciden")]
    for i, (a, b, c) in enumerate(rows):
        y = 420 + i * 44
        v.static(text(444, y, a, 14, TEXT))
        v.static(text(700, y, b, 15, PROCESS, weight="bold"))
        v.static(text(790, y, c, 13, TEXT_DIM))

    # Equipos (clic -> faceplate)
    card(v, 1128, 84, 448, 560, "Equipos", "clic para detalle")
    _equipment_row(v, "ov_p101", 124, T["estado_bomba"], PUMP_RANGES, "P-101", "Bomba de llenado",
                   T["txt_bomba"], "dlg_p101")
    _equipment_row(v, "ov_v101", 208, T["estado_valvula"],
                   [(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN)], "V-101", "Válvula de consumo",
                   T["txt_valvula"], "dlg_v101")
    _equipment_row(v, "ov_lt101", 292, T["b_fsensor"], [(0, 0, RUN), (1, 1, CRIT)], "LT-101",
                   "Transmisor de nivel", T["txt_sensor"], "dlg_lt101")
    _equipment_row(v, "ov_seg", 376, T["seguridades_ok"], [(0, 0, CRIT), (1, 1, RUN)], "Seguridades",
                   "Seta · fallo sensor · fallo arranque", T["txt_seguridades"], "")
    _equipment_row(v, "ov_res", 460, T["b_reserva"], [(0, 0, EQUIP_DARK), (1, 1, INFO)], "Consumo",
                   "Reserva ≤ 200 L / rearme ≥ 250 L", T["txt_consumo"], "")
    v.static(text(1144, 572, "Verde = en marcha / correcto · Gris = en reposo", 12, TEXT_DIM))
    v.static(text(1144, 594, "Ámbar = aviso · Rojo = fallo o alarma", 12, TEXT_DIM))

    # Alarmas activas + resumen IT
    card(v, 24, 664, 1084, 212, "Alarmas activas")
    alarm_table(v, "ov_alarms", 40, 704, 1052, 160)
    card(v, 1128, 664, 448, 212, "Última alarma IT (MQTT)", "solo lectura")
    for i, (label, tag) in enumerate((("Severidad", "it_severidad"), ("Estado", "it_estado"),
                                      ("Variable", "it_variable"), ("Mensaje", "it_mensaje"))):
        y = 724 + i * 36
        v.static(text(1148, y, label, 13, TEXT_DIM))
        value(v, f"ov_{tag}", T[tag], 1260, y, size=14, anchor="start")
    return v
