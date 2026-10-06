from __future__ import annotations

import json
import logging
import time

import paho.mqtt.client as mqtt

from config import BrokerConfig
from domain.models import PlcStatus, Reading

logger = logging.getLogger(__name__)

CONNECT_RETRY_MIN_S = 1.0
CONNECT_RETRY_MAX_S = 30.0
# Con el broker caido paho encola las publicaciones QoS 1: se acota (~6 min a 13 msg/s) para no agotar memoria
MAX_QUEUED_MESSAGES = 5000


class MqttPublisher:
    def __init__(self, broker: BrokerConfig, will_plc: str) -> None:
        self._broker = broker
        self._client = mqtt.Client(client_id=broker.client_id, clean_session=True)
        if broker.username:
            self._client.username_pw_set(broker.username, broker.password)
        self._client.will_set(
            f"{broker.topic_prefix}/{will_plc}/status",
            json.dumps({"ts": 0, "plc": will_plc, "online": False}),
            qos=broker.qos,
            retain=True,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.max_queued_messages_set(MAX_QUEUED_MESSAGES)
        self._dropped = 0

    def take_dropped(self) -> int:
        """Devuelve y reinicia el contador de mensajes descartados por cola llena."""
        count, self._dropped = self._dropped, 0
        return count

    def _publish(self, topic: str, payload: str, retain: bool = False) -> None:
        result = self._client.publish(topic, payload, qos=self._broker.qos, retain=retain)
        if result.rc == mqtt.MQTT_ERR_QUEUE_SIZE:
            self._dropped += 1

    def start(self) -> None:
        delay = CONNECT_RETRY_MIN_S
        while True:
            try:
                self._client.connect(self._broker.host, self._broker.port, keepalive=60)
                break
            except Exception as exc:
                logger.warning(
                    "MQTT no disponible en %s:%s (%s); reintento en %.0f s",
                    self._broker.host,
                    self._broker.port,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, CONNECT_RETRY_MAX_S)
        self._client.loop_start()
        logger.info("MQTT conectado a %s:%s", self._broker.host, self._broker.port)

    def publish_status(self, status: PlcStatus) -> None:
        topic = f"{self._broker.topic_prefix}/{status.plc}/status"
        payload = json.dumps({"ts": status.ts, "plc": status.plc, "online": status.online})
        self._publish(topic, payload, retain=True)

    def publish_reading(self, plc: str, reading: Reading) -> None:
        topic = f"{self._broker.topic_prefix}/{plc}/telemetry/{reading.variable}"
        payload = json.dumps(
            {
                "ts": reading.ts,
                "plc": plc,
                "variable": reading.variable,
                "value": reading.value,
                "unit": reading.unit,
                "q": reading.q,
            }
        )
        self._publish(topic, payload)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
