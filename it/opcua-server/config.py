from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_broker: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_pass: str | None
    opc_endpoint: str
    opc_port: int
    opc_user: str
    opc_password: str
    pki_dir: str


def load_config() -> Config:
    return Config(
        mqtt_broker=os.getenv("MQTT_BROKER", "127.0.0.1"),
        mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
        mqtt_user=os.getenv("MQTT_USER"),
        mqtt_pass=os.getenv("MQTT_PASS"),
        opc_endpoint=os.getenv("OPC_ENDPOINT", "0.0.0.0"),
        opc_port=int(os.getenv("OPC_PORT", "4840")),
        opc_user=os.getenv("OPC_USER", "otbridge"),
        opc_password=os.getenv("OPC_PASSWORD", ""),
        pki_dir=os.getenv("OPC_PKI_DIR", "/app/pki"),
    )
