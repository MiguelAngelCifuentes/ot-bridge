from __future__ import annotations

import logging
import time

from pymodbus.client import ModbusTcpClient

from config import PlcConfig
from domain.models import PlcStatus, Reading

logger = logging.getLogger(__name__)

RECONNECT_MIN_S = 1.0
RECONNECT_MAX_S = 30.0


def to_int16(raw: int) -> int:
    """Los registros %MW del PLC son INT (con signo); Modbus los entrega como uint16."""
    return raw - 0x10000 if raw >= 0x8000 else raw


class ModbusPoller:
    def __init__(self, plc: PlcConfig) -> None:
        self._plc = plc
        self._client: ModbusTcpClient | None = None
        self._last_values: dict[str, int] = {}
        self._backoff_s = RECONNECT_MIN_S
        self._retry_at = 0.0

    @property
    def plc(self) -> PlcConfig:
        return self._plc

    def _connect(self) -> ModbusTcpClient:
        client = ModbusTcpClient(self._plc.host, port=self._plc.port, timeout=2)
        if not client.connect():
            raise ConnectionError(f"sin conexión a {self._plc.host}:{self._plc.port}")
        self._client = client
        logger.info("Modbus conectado a %s:%s", self._plc.host, self._plc.port)
        return client

    def _close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _offline_readings(self, ts: int) -> list[Reading]:
        return [
            Reading(
                variable=register.name,
                value=self._last_values.get(register.name, 0),
                unit=register.unit,
                ts=ts,
                q=0,
            )
            for register in self._plc.registers
        ]

    def poll(self) -> tuple[list[Reading], PlcStatus]:
        ts = int(time.time())
        now = time.monotonic()
        if now < self._retry_at:
            return self._offline_readings(ts), PlcStatus(plc=self._plc.name, online=False, ts=ts)

        try:
            client = self._client or self._connect()
            base = self._plc.registers[0].address
            result = client.read_holding_registers(
                address=base,
                count=len(self._plc.registers),
                device_id=self._plc.unit_id,
            )
            if result.isError():
                raise RuntimeError(str(result))

            readings: list[Reading] = []
            for register, raw in zip(self._plc.registers, result.registers):
                value = to_int16(int(raw))
                self._last_values[register.name] = value
                readings.append(Reading(variable=register.name, value=value, unit=register.unit, ts=ts, q=1))
            self._backoff_s = RECONNECT_MIN_S
            return readings, PlcStatus(plc=self._plc.name, online=True, ts=ts)
        except Exception as exc:
            self._close()
            self._retry_at = now + self._backoff_s
            logger.warning(
                "Lectura Modbus de %s:%s fallida (%s); reintento en %.0f s",
                self._plc.host,
                self._plc.port,
                exc,
                self._backoff_s,
            )
            self._backoff_s = min(self._backoff_s * 2, RECONNECT_MAX_S)
            return self._offline_readings(ts), PlcStatus(plc=self._plc.name, online=False, ts=ts)
