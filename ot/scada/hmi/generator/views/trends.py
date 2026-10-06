"""V6 · Tendencias: historico real (DAQ en SQLite de FUXA) de nivel, caudales, bomba y equipos."""
from __future__ import annotations

from lib import View, card, chart
from model import CHART_IDS
from views.common import VIEW_IDS, status_bar


def build() -> View:
    v = View(VIEW_IDS["trends"], "Tendencias")
    status_bar(v, "TENDENCIAS")
    panels = [("nivel", "Nivel TK-101", 24, 84), ("caudales", "Caudales y balance", 812, 84),
              ("bomba", "Bomba P-101: velocidad y consigna", 24, 484), ("equipos", "Estado de equipos", 812, 484)]
    for key, title, x, y in panels:
        card(v, x, y, 764, 392, title, "historial: rueda del ratón = zoom")
        chart(v, f"tr_{key}", CHART_IDS[key], x + 12, y + 40, 740, 340)
    return v
