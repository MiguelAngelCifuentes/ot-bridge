from __future__ import annotations

import logging
import signal
import time

from adapters.modbus_poller import ModbusPoller
from adapters.mqtt_publisher import MqttPublisher
from app.poll_loop import PollLoop
from config import load_config
from domain.models import PlcStatus

logger = logging.getLogger("gateway")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    logger.info(
        "Gateway arrancando: %d PLC(s), broker %s:%s",
        len(config.plcs),
        config.broker.host,
        config.broker.port,
    )

    publisher = MqttPublisher(config.broker, will_plc=config.plcs[0].name)
    publisher.start()

    pollers = [ModbusPoller(plc) for plc in config.plcs]
    loop = PollLoop(pollers, publisher)

    def handle_signal(signum, _frame):
        logger.info("Señal %s recibida; parando", signum)
        loop.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        loop.run()
    finally:
        for plc in config.plcs:
            publisher.publish_status(PlcStatus(plc=plc.name, online=False, ts=int(time.time())))
        time.sleep(0.2)
        publisher.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
