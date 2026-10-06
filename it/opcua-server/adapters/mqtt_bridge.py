from __future__ import annotations

import json
import logging
import threading
import time

import paho.mqtt.client as mqtt

from config import Config

logger = logging.getLogger(__name__)

TELEMETRY_TOPIC = "factory/+/telemetry/#"
STATUS_TOPIC = "factory/+/status"


class MqttBridge:
    """Suscriptor MQTT: guarda el último valor de cada variable y el estado del PLC."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._values: dict[str, tuple[float, int]] = {}      # clave plc|variable -> (valor, ts)
        self._online: dict[str, bool] = {}
        self._lock = threading.Lock()
        self._client = mqtt.Client(client_id="opcua-bridge", clean_session=True)
        if config.mqtt_user:
            self._client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

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
                data = json.loads(message.payload)
                with self._lock:
                    self._online[str(data["plc"])] = bool(data["online"])
                return
            data = json.loads(message.payload)
            if int(data.get("q", 1)) != 1:
                return
            key = f'{data["plc"]}|{data["variable"]}'
            with self._lock:
                self._values[key] = (float(data["value"]), int(data.get("ts", 0)))
        except Exception:
            logger.warning("Mensaje MQTT descartado en %s", message.topic)

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

    def snapshot(self) -> dict:
        with self._lock:
            return {"values": dict(self._values), "online": dict(self._online)}

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
