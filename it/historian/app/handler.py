from __future__ import annotations

import json
import logging

from adapters.influx_writer import InfluxWriter
from domain.models import PlcStatus, Reading, TwinState

logger = logging.getLogger(__name__)


def _parse_status(topic: str, payload: bytes) -> PlcStatus | None:
    try:
        data = json.loads(payload)
        return PlcStatus(plc=str(data["plc"]), online=bool(data["online"]), ts=int(data["ts"]))
    except (ValueError, KeyError, TypeError):
        logger.warning("Mensaje de status malformado en %s; descartado", topic)
        return None


def _parse_reading(topic: str, payload: bytes) -> Reading | None:
    try:
        data = json.loads(payload)
        reading = Reading(
            plc=str(data["plc"]),
            variable=str(data["variable"]),
            value=int(data["value"]),
            unit=str(data.get("unit", "")),
            ts=int(data["ts"]),
            q=int(data.get("q", 1)),
        )
    except (ValueError, KeyError, TypeError):
        logger.warning("Telemetria malformada en %s; descartada", topic)
        return None

    if reading.q != 1:
        logger.debug("Lectura q=%s descartada (%s/%s)", reading.q, reading.plc, reading.variable)
        return None
    return reading


def _parse_twin(topic: str, payload: bytes) -> TwinState | None:
    try:
        data = json.loads(payload)
        return TwinState(
            plc=str(data["plc"]),
            ts=int(data["ts"]),
            level_real=float(data["level_real"]),
            level_model=float(data["level_model"]),
            deviation=float(data["deviation"]),
            leak_lpm=float(data["leak_lpm"]),
            threshold=float(data["threshold"]),
            alarmed=bool(data["alarmed"]),
        )
    except (ValueError, KeyError, TypeError):
        logger.warning("Estado del gemelo malformado en %s; descartado", topic)
        return None


def parse_message(topic: str, payload: bytes) -> Reading | PlcStatus | TwinState | None:
    if topic.endswith("/twin/state"):
        return _parse_twin(topic, payload)
    if topic.endswith("/status"):
        return _parse_status(topic, payload)
    if "/telemetry/" in topic:
        return _parse_reading(topic, payload)
    return None


class MessageHandler:
    def __init__(self, writer: InfluxWriter) -> None:
        self._writer = writer

    def handle(self, topic: str, payload: bytes) -> None:
        message = parse_message(topic, payload)
        if isinstance(message, Reading):
            self._writer.add_reading(message)
        elif isinstance(message, PlcStatus):
            self._writer.add_status(message)
        elif isinstance(message, TwinState):
            self._writer.add_twin_state(message)
