"""Elementos comunes: barra de estado superior, identificadores de vistas y navegacion."""
from __future__ import annotations

from lib import (CRIT, EMERG, EQUIP_DARK, HEADER, INFO, MANUAL, PANEL, PANEL_EDGE, RUN, TEXT, TEXT_DIM, WARN,
                 View, lamp, rect, text, value)
from model import T

VIEW_IDS = {
    "overview": "v_otb_overview", "process": "v_otb_process", "control": "v_otb_control",
    "alarms": "v_otb_alarms", "trends": "v_otb_trends", "diagnostics": "v_otb_diagnostics",
    "dlg_p101": "v_dlg_p101", "dlg_v101": "v_dlg_v101", "dlg_lt101": "v_dlg_lt101",
    "dlg_manual": "v_dlg_manual", "dlg_marcha": "v_dlg_marcha", "dlg_reset": "v_dlg_reset",
    "dlg_rearme": "v_dlg_rearme",
}

# Estado de planta: -1 sin comunicacion, 0 parada, 1 en marcha, 2 fallo, 3 emergencia
PLANT_RANGES = [(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN), (2, 2, CRIT), (3, 3, EMERG)]
PUMP_RANGES = [(-1, -1, "#3A3F47"), (0, 0, EQUIP_DARK), (1, 1, RUN), (2, 2, CRIT), (3, 3, WARN)]


def status_bar(v: View, title: str) -> None:
    """Franja superior comun: titulo de la vista, estado de planta, modo, consumo y comunicaciones."""
    w = v.width
    v.static(rect(0, 0, w, 64, HEADER, "none", 0))
    v.static(text(24, 40, title, 22, TEXT, weight="bold"))
    x = w - 1040
    # Estado de planta
    lamp(v, "sb_planta", T["estado_planta"], x, 12, 230, 40, ranges=PLANT_RANGES, rx=6)
    v.static(text(x + 12, 26, "PLANTA", 10, "#FFFFFF", extra='letter-spacing="1" opacity="0.75"'))
    value(v, "sb_planta_txt", T["txt_planta"], x + 115, 45, size=16, color="#FFFFFF", weight="bold")
    # Modo
    x += 242
    lamp(v, "sb_modo", T["b_manual"], x, 12, 180, 40, ranges=[(0, 0, "#3A4452"), (1, 1, MANUAL)], rx=6)
    v.static(text(x + 12, 26, "MODO", 10, "#FFFFFF", extra='letter-spacing="1" opacity="0.75"'))
    value(v, "sb_modo_txt", T["txt_modo"], x + 90, 45, size=16, color="#FFFFFF", weight="bold")
    # Consumo
    x += 192
    lamp(v, "sb_consumo", T["b_reserva"], x, 12, 180, 40, ranges=[(0, 0, "#3A4452"), (1, 1, INFO)], rx=6)
    v.static(text(x + 12, 26, "CONSUMO", 10, "#FFFFFF", extra='letter-spacing="1" opacity="0.75"'))
    value(v, "sb_consumo_txt", T["txt_consumo"], x + 90, 45, size=15, color="#FFFFFF", weight="bold")
    # Comunicaciones
    x += 192
    v.static(rect(x, 12, 390, 40, "#262C34", PANEL_EDGE, 6))
    lamp(v, "sb_plc", T["plc_online"], x + 14, 25, 14, 14, shape="circle", ranges=[(0, 0, CRIT), (1, 1, RUN)])
    v.static(text(x + 36, 37, "PLC", 13, TEXT_DIM, weight="bold"))
    value(v, "sb_plc_txt", T["txt_plc"], x + 70, 37, size=13, anchor="start")
    lamp(v, "sb_it", T["it_online"], x + 226, 25, 14, 14, shape="circle", ranges=[(0, 0, CRIT), (1, 1, RUN)])
    v.static(text(x + 248, 37, "IT", 13, TEXT_DIM, weight="bold"))
    value(v, "sb_it_txt", T["txt_it"], x + 270, 37, size=13, anchor="start")


def kpi(v: View, name: str, x, y, w, h, label: str, tag: str, unit: str, digits: int = 1, color="#FFFFFF",
        size=34) -> None:
    """Tarjeta de indicador: etiqueta arriba, valor grande con unidad."""
    v.static(rect(x, y, w, h, PANEL, PANEL_EDGE, 8))
    v.static(text(x + 16, y + 26, label.upper(), 12, TEXT_DIM, weight="bold", extra='letter-spacing="1"'))
    value(v, name, tag, x + w / 2, y + h - 22, size=size, color=color, unit=unit, digits=digits)


def tank(v: View, name: str, x, y, w, h, *, marks: bool = True, big: bool = True) -> None:
    """Deposito TK-101: relleno proporcional (0-1000 L), valor y marcas de los setpoints del PLC."""
    from lib import WATER, progress
    from model import SP
    v.static(rect(x - 6, y - 6, w + 12, h + 12, "#1B2027", "#6B7785", 10, 2))
    progress(v, f"{name}_fill", T["LT101_nivel"], x, y, w, h, vmin=0, vmax=1000, color=WATER)
    if marks:
        labels = {"SP_ALARMA_ALTA": ("950 ALTA", CRIT), "SP_LLENO": ("900 LLENO", TEXT_DIM),
                  "SP_ARRANQUE_BOMBA": ("300 ARRANQUE", TEXT_DIM), "SP_RESERVA": ("200 RESERVA", INFO),
                  "SP_ALARMA_BAJA": ("100 BAJA", CRIT)}
        for key, (label, color) in labels.items():
            yy = y + h - SP[key] / 1000 * h
            v.static(f'<line x1="{x}" y1="{yy}" x2="{x + w + 14}" y2="{yy}" stroke="{color}" stroke-width="1.5" '
                     f'stroke-dasharray="6 4"/>')
            v.static(text(x + w + 18, yy + 4, label, 11, color))
    size = 40 if big else 26
    value(v, f"{name}_val", T["LT101_nivel"], x + w / 2, y + (90 if big else 60), size=size, color="#FFFFFF", unit="L",
          digits=0, weight="bold")
    value(v, f"{name}_pct", T["nivel_pct"], x + w / 2, y + (122 if big else 84), size=16,
          color="#DDE6F0", unit="%", digits=0)
