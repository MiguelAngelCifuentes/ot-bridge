from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    api_url: str
    api_key: str | None
    api_poll_interval_s: int
    state_file: str


def load_config() -> Config:
    return Config(
        mqtt_broker=os.getenv("MQTT_BROKER", "127.0.0.1"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_user=os.getenv("MQTT_USER"),
        mqtt_pass=os.getenv("MQTT_PASS"),
        api_url=os.getenv("API_URL", "http://127.0.0.1:8080"),
        api_key=os.getenv("API_KEY") or None,
        api_poll_interval_s=int(os.getenv("API_POLL_INTERVAL_S", "30")),
        state_file=os.getenv("STATE_FILE", "/app/data/alarm_state.json"),
    )
