from __future__ import annotations

import logging
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from config import Config

logger = logging.getLogger(__name__)

CONNECT_RETRY_MIN_S = 1.0
CONNECT_RETRY_MAX_S = 30.0
SUBSCRIPTIONS = (
    ("factory/+/telemetry/#", 1),
    ("factory/+/status", 1),
    ("factory/+/twin/state", 0),
)


class MqttSubscriber:
    def __init__(self, config: Config, on_message: Callable[[str, bytes], None]) -> None:
        self._config = config
        self._on_message = on_message
        self._client = mqtt.Client(client_id="historian", clean_session=False)
        if config.mqtt_user:
            self._client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_mqtt_message

    def _on_connect(self, client, _userdata, _flags, rc):
        if rc == 0:
            for topic, qos in SUBSCRIPTIONS:
                client.subscribe(topic, qos=qos)
            logger.info("Suscrito a %s", ", ".join(topic for topic, _ in SUBSCRIPTIONS))
        else:
            logger.error("MQTT rechazo la conexion (rc=%s)", rc)

    def _on_disconnect(self, _client, _userdata, rc):
        if rc != 0:
            logger.warning("Desconectado del broker (rc=%s); reconexion automatica", rc)

    def _on_mqtt_message(self, _client, _userdata, message):
        try:
            self._on_message(message.topic, message.payload)
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

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
