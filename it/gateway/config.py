from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RegisterConfig:
    address: int
    name: str
    unit: str


@dataclass(frozen=True)
class PlcConfig:
    name: str
    host: str
    port: int
    unit_id: int
    poll_interval_ms: int
    registers: tuple[RegisterConfig, ...]


@dataclass(frozen=True)
class BrokerConfig:
    host: str
    port: int
    qos: int
    client_id: str
    topic_prefix: str
    username: str | None
    password: str | None


@dataclass(frozen=True)
class GatewayConfig:
    broker: BrokerConfig
    plcs: tuple[PlcConfig, ...]


def load_config(path: str | Path | None = None) -> GatewayConfig:
    config_path = Path(path or os.getenv("GATEWAY_CONFIG", "config.yaml"))
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not raw:
        raise ValueError(f"Configuración vacía o ilegible: {config_path}")

    broker_raw = raw.get("broker") or {}
    broker = BrokerConfig(
        host=os.getenv("MQTT_BROKER", str(broker_raw.get("host", "127.0.0.1"))),
        port=int(os.getenv("MQTT_PORT", broker_raw.get("port", 1883))),
        qos=int(os.getenv("MQTT_QOS", broker_raw.get("qos", 1))),
        client_id=os.getenv("MQTT_CLIENT_ID", str(broker_raw.get("client_id", "gateway"))),
        topic_prefix=str(broker_raw.get("topic_prefix", "factory")),
        username=os.getenv("MQTT_USER"),
        password=os.getenv("MQTT_PASS"),
    )

    plcs_raw = raw.get("plcs") or []
    if not plcs_raw:
        raise ValueError(f"{config_path} no define ningún PLC en 'plcs'")

    plc_host_override = os.getenv("PLC_HOST")
    plcs: list[PlcConfig] = []
    for plc_raw in plcs_raw:
        registers = tuple(
            RegisterConfig(
                address=int(register["address"]),
                name=str(register["name"]),
                unit=str(register.get("unit", "")),
            )
            for register in plc_raw.get("registers", [])
        )
        if not registers:
            raise ValueError(f"El PLC '{plc_raw.get('name')}' no define registros")
        addresses = [register.address for register in registers]
        if addresses != list(range(addresses[0], addresses[0] + len(addresses))):
            raise ValueError(
                f"Los registros de '{plc_raw.get('name')}' deben ser contiguos para lectura en bloque: {addresses}"
            )
        plcs.append(
            PlcConfig(
                name=str(plc_raw["name"]),
                host=plc_host_override or str(plc_raw["host"]),
                port=int(os.getenv("PLC_PORT", plc_raw.get("port", 502))),
                unit_id=int(os.getenv("PLC_UNIT_ID", plc_raw.get("unit_id", 1))),
                poll_interval_ms=int(plc_raw.get("poll_interval_ms", 1000)),
                registers=registers,
            )
        )

    return GatewayConfig(broker=broker, plcs=tuple(plcs))
