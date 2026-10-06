"""V5 · Alarmas: activas con ACK, historico filtrable y alarmas del motor IT (informativas)."""
from __future__ import annotations

from lib import TEXT_DIM, View, alarm_table, card, text, value
from model import T
from views.common import VIEW_IDS, status_bar


def build() -> View:
    v = View(VIEW_IDS["alarms"], "Alarmas")
    status_bar(v, "ALARMAS")
    card(v, 24, 84, 1552, 380, "Alarmas activas", "ACK: operador o supervisor")
    alarm_table(v, "al_active", 40, 124, 1520, 326, filters=True)
    card(v, 24, 484, 1100, 392, "Histórico de alarmas", "filtrable por fecha")
    alarm_table(v, "al_history", 40, 524, 1068, 340, history=True, filters=True)

    card(v, 1144, 484, 432, 392, "Alarmas IT (MQTT)", "informativas")
    for i, (label, tag) in enumerate((("Severidad", "it_severidad"), ("Estado", "it_estado"),
                                      ("Variable", "it_variable"), ("Mensaje", "it_mensaje"))):
        y = 548 + i * 44
        v.static(text(1164, y, label, 13, TEXT_DIM))
        value(v, f"al_{tag}", T[tag], 1270, y, size=15, anchor="start")
    notes = ["Última alarma publicada por el motor de alarmas IT",
             "y el gemelo digital en factory/alarms/events.",
             "Se gestionan (ACK) desde la API/Grafana en IT;",
             "aquí son solo informativas: el mando es OT."]
    for i, n in enumerate(notes):
        v.static(text(1164, 740 + i * 22, n, 12, TEXT_DIM))
    return v
