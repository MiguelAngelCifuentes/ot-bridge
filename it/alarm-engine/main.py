from __future__ import annotations

import logging
import signal
import threading

from adapters.api_client import ApiClient
from adapters.mqtt_io import MqttIo
from adapters.state_store import StateStore
from app.service import AlarmService
from config import load_config

logger = logging.getLogger("alarm-engine")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    logger.info(
        "Alarm engine arrancando: broker %s:%s, api %s (refresh %d s)",
        config.mqtt_broker,
        config.mqtt_port,
        config.api_url,
        config.api_poll_interval_s,
    )

    api_client = ApiClient(config.api_url, config.api_key)
    mqtt_io = MqttIo(config)
    store = StateStore(config.state_file)
    service = AlarmService(mqtt_io, api_client, config.api_poll_interval_s, store)
    mqtt_io.set_telemetry_handler(service.handle_telemetry)
    mqtt_io.set_status_handler(service.handle_status)

    stop = threading.Event()

    def handle_signal(_signum, _frame):
        logger.info("Senal recibida; parando alarm engine")
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    service.start()
    mqtt_io.start()
    stop.wait()

    mqtt_io.stop()
    service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
