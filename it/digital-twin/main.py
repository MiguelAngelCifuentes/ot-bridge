from __future__ import annotations

import json
import logging
import signal
import threading
from pathlib import Path

from adapters.mqtt_io import MqttIo
from config import load_config
from domain.twin import MassBalanceTwin

logger = logging.getLogger("digital-twin")

HEARTBEAT_FILE = Path("/tmp/heartbeat")     # healthcheck: el proceso sigue vivo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    logger.info("Gemelo digital arrancando (umbral %.0f L, ganancia %.4f/s, divisor de caudal %.0f)",
                config.umbral_l, config.gain, config.flow_divisor)

    twin = MassBalanceTwin(config.umbral_l, config.gain, config.flow_divisor)
    mqtt = MqttIo(config)

    def handle(topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            logger.warning("Payload malformado en %s; descartado", topic)
            return
        try:
            plc = str(data["plc"])
            variable = str(data["variable"])
            value = float(data["value"])
            ts = int(data["ts"])
            q = int(data.get("q", 1))
        except (KeyError, TypeError, ValueError):
            logger.warning("Campos invalidos en %s; descartado", topic)
            return
        if q != 1 or plc != "plc01":
            return

        result = twin.update(variable, value, ts)
        if result is None:
            return
        mqtt.publish_state(plc, result.state)
        if result.event is not None:
            mqtt.publish_event(plc, "balance", "high", result.event, result.message)

    mqtt.set_handler(handle)
    mqtt.start()
    # El modelo arranca sincronizado con el nivel real: cualquier alarma de balance previa queda obsoleta
    mqtt.publish_event("plc01", "balance", "high", "RESOLVED", "Gemelo reiniciado: modelo resincronizado")

    stop = threading.Event()

    def handle_signal(_signum, _frame):
        logger.info("Senal recibida; parando")
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not stop.wait(10):
        HEARTBEAT_FILE.touch()
    mqtt.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
