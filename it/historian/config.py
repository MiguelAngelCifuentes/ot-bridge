from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    influx_host: str
    influx_port: int
    influx_db: str
    influx_user: str | None
    influx_password: str | None


def load_config() -> Config:
    return Config(
        mqtt_broker=os.getenv("MQTT_BROKER", "127.0.0.1"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_user=os.getenv("MQTT_USER"),
        mqtt_pass=os.getenv("MQTT_PASS"),
        influx_host=os.getenv("INFLUX_HOST", "127.0.0.1"),
        influx_port=int(os.getenv("INFLUX_PORT", "8086")),
        influx_db=os.getenv("INFLUX_DB", "plant"),
        influx_user=os.getenv("INFLUX_USER") or None,
        influx_password=os.getenv("INFLUX_PASSWORD") or None,
    )
