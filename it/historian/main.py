from __future__ import annotations

import logging
import signal
import threading

from adapters.influx_writer import InfluxWriter
from adapters.mqtt_subscriber import MqttSubscriber
from app.handler import MessageHandler
from config import load_config

logger = logging.getLogger("historian")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    logger.info(
        "Historian arrancando: broker %s:%s, influx %s:%s/%s",
        config.mqtt_broker,
        config.mqtt_port,
        config.influx_host,
        config.influx_port,
        config.influx_db,
    )

    writer = InfluxWriter(config)
    writer.start()

    handler = MessageHandler(writer)
    subscriber = MqttSubscriber(config, handler.handle)

    stop = threading.Event()

    def handle_signal(_signum, _frame):
        logger.info("Senal recibida; parando historian")
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    subscriber.start()
    stop.wait()

    subscriber.stop()
    writer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
