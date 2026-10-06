from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from config import Config
from domain.twin import TwinState

logger = logging.getLogger(__name__)

TELEMETRY_TOPIC = "factory/+/telemetry/#"
EVENTS_TOPIC = "factory/alarms/events"
STATE_TOPIC = "factory/{plc}/twin/state"
ALARM_CODE = "gemelo:balance"


class MqttIo:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._handler: Callable[[str, bytes], None] | None = None
        self._client = mqtt.Client(client_id="digital-twin", clean_session=True)
        if config.mqtt_user:
            self._client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def set_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._handler = handler

    def _on_connect(self, client, _userdata, _flags, rc):
        if rc == 0:
            client.subscribe(TELEMETRY_TOPIC, qos=1)
            logger.info("Suscrito a %s", TELEMETRY_TOPIC)
        else:
            logger.error("MQTT rechazo la conexion (rc=%s)", rc)

    def _on_message(self, _client, _userdata, message):
        if self._handler is None:
            return
        try:
            self._handler(message.topic, message.payload)
        except Exception:
            logger.exception("Error procesando mensaje de %s", message.topic)

    def start(self) -> None:
        delay = 1.0
        while True:
            try:
                self._client.connect(self._config.mqtt_broker, self._config.mqtt_port, keepalive=60)
                break
            except Exception as exc:
                logger.warning("MQTT no disponible (%s); reintento en %.0f s", exc, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        self._client.loop_start()

    def publish_event(self, plc: str, variable: str, severity: str, state: str, message: str) -> None:
        payload = json.dumps(
            {"ts": int(time.time()), "plc": plc, "variable": variable,
             "severity": severity, "state": state, "message": message, "code": ALARM_CODE})
        self._client.publish(EVENTS_TOPIC, payload, qos=1)

    def publish_state(self, plc: str, state: TwinState) -> None:
        payload = json.dumps(
            {"ts": state.ts, "plc": plc, "level_real": state.level_real, "level_model": state.level_model,
             "deviation": state.deviation, "leak_lpm": state.leak_lpm, "threshold": state.threshold,
             "alarmed": state.alarmed})
        self._client.publish(STATE_TOPIC.format(plc=plc), payload, qos=0)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
