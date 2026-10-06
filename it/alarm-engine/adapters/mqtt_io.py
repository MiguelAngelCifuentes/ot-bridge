from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from config import Config

logger = logging.getLogger(__name__)

TELEMETRY_TOPIC = "factory/+/telemetry/#"
STATUS_TOPIC = "factory/+/status"
EVENTS_TOPIC = "factory/alarms/events"
CONNECT_RETRY_MIN_S = 1.0
CONNECT_RETRY_MAX_S = 30.0


class MqttIo:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._telemetry_handler: Callable[[str, bytes], None] | None = None
        self._status_handler: Callable[[str, bytes], None] | None = None
        self._client = mqtt.Client(client_id="alarm-engine", clean_session=True)
        if config.mqtt_user:
            self._client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def set_telemetry_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._telemetry_handler = handler

    def set_status_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._status_handler = handler

    def _on_connect(self, client, _userdata, _flags, rc):
        if rc == 0:
            client.subscribe(TELEMETRY_TOPIC, qos=1)
            client.subscribe(STATUS_TOPIC, qos=1)
            logger.info("Suscrito a %s y %s", TELEMETRY_TOPIC, STATUS_TOPIC)
        else:
            logger.error("MQTT rechazo la conexion (rc=%s)", rc)

    def _on_message(self, _client, _userdata, message):
        try:
            if message.topic.endswith("/status"):
                if self._status_handler is not None:
                    self._status_handler(message.topic, message.payload)
            elif self._telemetry_handler is not None:
                self._telemetry_handler(message.topic, message.payload)
        except Exception:
            logger.exception("Error procesando mensaje de %s", message.topic)

    def start(self) -> None:
        delay = CONNECT_RETRY_MIN_S
        while True:
            try:
                self._client.connect(self._config.mqtt_broker, self._config.mqtt_port, keepalive=60)
                break
            except Exception as exc:
                logger.warning(
                    "MQTT no disponible en %s:%s (%s); reintento en %.0f s",
                    self._config.mqtt_broker,
                    self._config.mqtt_port,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, CONNECT_RETRY_MAX_S)
        self._client.loop_start()
        logger.info("MQTT conectado a %s:%s", self._config.mqtt_broker, self._config.mqtt_port)

    def publish_event(self, plc: str, variable: str, severity: str, state: str, message: str, code: str) -> None:
        payload = json.dumps(
            {
                "ts": int(time.time()),
                "plc": plc,
                "variable": variable,
                "severity": severity,
                "state": state,
                "message": message,
                "code": code,
            }
        )
        self._client.publish(EVENTS_TOPIC, payload, qos=1)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
