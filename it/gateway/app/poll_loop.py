from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from adapters.modbus_poller import ModbusPoller
from adapters.mqtt_publisher import MqttPublisher

logger = logging.getLogger(__name__)

# Latido para el healthcheck de Docker: indica que el bucle sigue vivo (no que el PLC responda)
HEARTBEAT_FILE = Path("/tmp/heartbeat")
DROP_REPORT_S = 60.0


class PollLoop:
    def __init__(self, pollers: list[ModbusPoller], publisher: MqttPublisher) -> None:
        self._pollers = pollers
        self._publisher = publisher
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval_s = min(poller.plc.poll_interval_ms for poller in self._pollers) / 1000.0
        next_report = time.monotonic() + DROP_REPORT_S
        while not self._stop.is_set():
            cycle_start = time.monotonic()
            for poller in self._pollers:
                readings, status = poller.poll()
                self._publisher.publish_status(status)
                for reading in readings:
                    self._publisher.publish_reading(poller.plc.name, reading)
            HEARTBEAT_FILE.touch()
            if cycle_start >= next_report:
                dropped = self._publisher.take_dropped()
                if dropped:
                    logger.warning("Cola MQTT llena: %d mensajes descartados en el ultimo minuto", dropped)
                next_report = cycle_start + DROP_REPORT_S
            elapsed = time.monotonic() - cycle_start
            self._stop.wait(max(0.0, interval_s - elapsed))
