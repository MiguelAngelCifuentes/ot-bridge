"""V7 · Diagnostico (supervisor): comunicaciones, registros Modbus, bits de estado y constantes del PLC."""
from __future__ import annotations

from lib import CRIT, PANEL_EDGE, PROCESS, RUN, TEXT, TEXT_DIM, View, card, lamp, line, text, value
from model import BITS, CONSTANTS, PLC_TAGS, T
from views.common import VIEW_IDS, status_bar


def build() -> View:
    v = View(VIEW_IDS["diagnostics"], "Diagnóstico")
    status_bar(v, "DIAGNÓSTICO")

    card(v, 24, 84, 520, 250, "Comunicaciones")
    rows = [("PLC_Tanque", "Modbus TCP · unit 1 · sondeo 1 s", "plc_online", "txt_plc"),
            ("IT-Broker", "MQTT factory/alarms/events (lectura)", "it_online", "txt_it")]
    for i, (name, desc, lamp_tag, txt) in enumerate(rows):
        y = 134 + i * 90
        lamp(v, f"dg_{name}", T[lamp_tag], 44, y, 28, 28, shape="circle", ranges=[(0, 0, CRIT), (1, 1, RUN)])
        v.static(text(88, y + 14, name, 16, TEXT, weight="bold"))
        v.static(text(88, y + 36, desc, 12, TEXT_DIM))
        value(v, f"dg_{name}_txt", T[txt], 524, y + 20, size=14, anchor="end", weight="bold")

    card(v, 564, 84, 1012, 470, "Registros Modbus (valor escalado)", "direcciones 1-based como en FUXA")
    heads = (("Tag", 584), ("Registro", 790), ("Dir.", 890), ("Valor", 1060), ("Descripción", 1100))
    for h, x in heads:
        v.static(text(x, 136, h, 12, TEXT_DIM, "end" if h == "Valor" else "start", "bold"))
    for i, t in enumerate(PLC_TAGS):
        y = 164 + i * 31
        v.static(line(584, y + 9, 1556, y + 9, PANEL_EDGE, 1))
        v.static(text(584, y, t.name, 13, TEXT))
        v.static(text(790, y, f"MW{100 + i}", 13, TEXT_DIM))
        v.static(text(890, y, str(t.address), 13, TEXT_DIM))
        value(v, f"dg_reg_{t.name}", t.id, 1060, y, size=14, color=PROCESS, anchor="end",
              digits=2 if t.divisor > 1 else 0)
        v.static(text(1100, y, t.description.split(" (")[0], 12, TEXT_DIM))

    card(v, 24, 354, 520, 522, "Registro de estado MW105 (hmi_estado)")
    v.static(text(44, 400, "Valor bruto:", 14, TEXT_DIM))
    value(v, "dg_estado_raw", T["PLC_estado"], 140, 400, size=16, color=PROCESS, anchor="start", digits=0)
    for i, (bit, var, desc) in enumerate(BITS):
        y = 424 + i * 44
        lamp(v, f"dg_bit_{bit}", T["PLC_estado"], 44, y, 26, 26, bit=bit, on=PROCESS, off="#3A4452", rx=4)
        v.static(text(84, y + 18, f"{bit:>3}", 13, TEXT_DIM))
        v.static(text(124, y + 18, var, 14, TEXT, weight="bold"))
        v.static(text(300, y + 18, desc, 12, TEXT_DIM))

    card(v, 564, 574, 1012, 302, "Constantes del programa PLC (ot/plc/pous/programs/main.st)")
    for i, (name, val, desc) in enumerate(CONSTANTS):
        y = 626 + i * 27
        v.static(text(584, y, name, 13, TEXT))
        v.static(text(840, y, val, 13, PROCESS, weight="bold"))
        v.static(text(1000, y, desc, 12, TEXT_DIM))
    return v
