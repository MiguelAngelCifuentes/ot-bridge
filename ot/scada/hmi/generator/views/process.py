"""V2 · Proceso: P&ID vivo. Fuente -> P-101 (llenado) -> FT-101 -> TK-101 -> FT-102 -> V-101 (consumo)."""
from __future__ import annotations

from lib import (EQUIP_DARK, INFO, MANUAL, PANEL_EDGE, PROCESS, RUN, TEXT, TEXT_DIM, View, card, ev_dialog,
                 lamp, pipe, rect, text, value)
from model import T
from views.common import PUMP_RANGES, VIEW_IDS, status_bar, tank

BUBBLE = "#20262E"


def instrument(v: View, name: str, cx, cy, tag_label: str, tag: str, unit: str, digits: int, dialog: str = "",
               above: bool = False):
    """Burbuja ISA de instrumento con su valor al lado (o encima si no hay sitio)."""
    events = [ev_dialog(VIEW_IDS[dialog])] if dialog else None
    lamp(v, f"{name}_b", T["plc_online"], cx - 30, cy - 30, 60, 60, shape="circle",
         ranges=[(0, 0, "#3A3F47"), (1, 1, BUBBLE)], stroke="#9AA4AF", events=events)
    v.static(text(cx, cy + 5, tag_label, 13, TEXT, "middle", "bold", extra='pointer-events="none"'))
    if above:
        value(v, f"{name}_v", tag, cx, cy - 42, size=20, color=PROCESS, unit=unit, digits=digits, weight="bold")
    else:
        value(v, f"{name}_v", tag, cx + 42, cy + 7, size=20, color=PROCESS, unit=unit, digits=digits,
              anchor="start", weight="bold")


def build() -> View:
    v = View(VIEW_IDS["process"], "Proceso")
    status_bar(v, "PROCESO · P&ID")
    card(v, 24, 84, 1552, 792, "Balsa TK-101 · llenado por bombeo y consumo por gravedad",
         "clic en P-101, V-101 o LT-101 para su detalle")

    # Acometida (fuente)
    v.static(rect(52, 596, 150, 78, "#2E343D", "#6B7785", 8, 2))
    v.static(text(127, 630, "ACOMETIDA", 14, TEXT, "middle", "bold"))
    v.static(text(127, 652, "fuente", 12, TEXT_DIM, "middle"))

    # Tuberias (el contenido fluye solo con caudal)
    pipe(v, "p_in1", "M202 635 L312 635", T["FT101_caudal"])
    pipe(v, "p_in2", "M408 635 L470 635 L470 170 L780 170 L780 232", T["FT101_caudal"])
    pipe(v, "p_out1", "M1040 740 L1222 740", T["FT102_caudal"])
    pipe(v, "p_out2", "M1298 740 L1420 740", T["FT102_caudal"])

    # Bomba P-101 (color por estado; clic -> faceplate)
    lamp(v, "pid_p101", T["estado_bomba"], 312, 587, 96, 96, shape="circle", ranges=PUMP_RANGES,
         stroke="#C9D1D9", events=[ev_dialog(VIEW_IDS["dlg_p101"])],
         blink=(0, 3, 3, "#FF9830", "#6B4A1F"))
    v.static('<path d="M338 612 L338 658 L384 635 Z" fill="#E6E9ED" pointer-events="none"/>')
    v.static(text(360, 710, "P-101", 16, TEXT, "middle", "bold"))
    value(v, "pid_p101_txt", T["txt_bomba"], 360, 734, size=14, weight="bold")
    value(v, "pid_p101_vel", T["P101_velocidad"], 360, 758, size=14, color=PROCESS, unit="% velocidad", digits=0)

    # Caudalimetros
    instrument(v, "pid_ft101", 470, 330, "FT-101", T["FT101_caudal"], "l/min", 1)
    instrument(v, "pid_ft102", 1360, 650, "FT-102", T["FT102_caudal"], "l/min", 1, above=True)
    v.static('<line x1="1360" y1="680" x2="1360" y2="740" stroke="#9AA4AF" stroke-width="1.5" stroke-dasharray="4 3"/>')

    # Deposito TK-101 con marcas de setpoints
    tank(v, "pid_tank", 700, 240, 330, 520)
    v.static(text(865, 800, "TK-101 · 1000 L", 16, TEXT, "middle", "bold"))
    instrument(v, "pid_lt101", 610, 520, "LT-101", T["LT101_ma"], "mA", 2, "dlg_lt101", above=True)
    v.static('<line x1="640" y1="520" x2="694" y2="520" stroke="#9AA4AF" stroke-width="1.5" stroke-dasharray="4 3"/>')

    # Valvula V-101 (mariposa) con actuador
    bowtie = "M1222 712 L1260 740 L1222 768 Z M1298 712 L1260 740 L1298 768 Z"
    lamp(v, "pid_v101", T["estado_valvula"], 1222, 712, 76, 56, shape="path", d=bowtie,
         ranges=[(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN)], stroke="#C9D1D9",
         events=[ev_dialog(VIEW_IDS["dlg_v101"])])
    v.static('<line x1="1260" y1="740" x2="1260" y2="694" stroke="#C9D1D9" stroke-width="3"/>')
    v.static(rect(1240, 676, 40, 20, "#4A525D", "#C9D1D9", 3, 2))
    v.static(text(1260, 800, "V-101", 16, TEXT, "middle", "bold"))
    value(v, "pid_v101_txt", T["txt_valvula"], 1260, 824, size=14, weight="bold")

    # Consumo
    v.static(rect(1420, 700, 132, 80, "#2E343D", "#6B7785", 8, 2))
    v.static(text(1486, 734, "CONSUMO", 14, TEXT, "middle", "bold"))
    value(v, "pid_consumo", T["txt_consumo"], 1486, 758, size=12, color=TEXT_DIM)

    # Distintivos de modo y reserva
    lamp(v, "pid_badge_manual", T["b_manual"], 1180, 130, 170, 36, ranges=[(0, 0, "#262C34"), (1, 1, MANUAL)], rx=18, stroke=PANEL_EDGE)
    value(v, "pid_badge_manual_t", T["txt_modo"], 1265, 154, size=14, color="#FFFFFF", weight="bold")
    lamp(v, "pid_badge_res", T["b_reserva"], 1370, 130, 180, 36, ranges=[(0, 0, "#262C34"), (1, 1, INFO)], rx=18, stroke=PANEL_EDGE)
    value(v, "pid_badge_res_t", T["txt_consumo"], 1460, 154, size=14, color="#FFFFFF", weight="bold")

    # Leyenda ISA-101
    ly = 836
    for i, (c, t) in enumerate(((RUN, "En marcha / abierta"), (EQUIP_DARK, "En reposo"),
                                ("#FF9830", "Orden sin confirmar"), ("#F2495C", "Fallo"),
                                ("#2F6FB0", "Agua en circulación"))):
        x = 52 + i * 250
        v.static(rect(x, ly - 12, 16, 16, c, "none", 3))
        v.static(text(x + 26, ly + 1, t, 13, TEXT_DIM))
    return v
