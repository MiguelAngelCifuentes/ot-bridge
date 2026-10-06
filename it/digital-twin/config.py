from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    umbral_l: float
    gain: float
    flow_divisor: float


def load_config() -> Config:
    return Config(
        mqtt_broker=os.getenv("MQTT_BROKER", "127.0.0.1"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_user=os.getenv("MQTT_USER"),
        mqtt_pass=os.getenv("MQTT_PASS"),
        umbral_l=float(os.getenv("UMBRAL_L", "20")),
        # Ganancia de correccion del observador (1/s)
        gain=float(os.getenv("TWIN_GAIN", "0.005")),
        # Los caudales del contrato son l/min x10 (hmi_caudal_* del PLC): l/min = valor / FLOW_DIVISOR
        flow_divisor=float(os.getenv("FLOW_DIVISOR", "10")),
    )
