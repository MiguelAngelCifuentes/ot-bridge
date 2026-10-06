from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from requests.exceptions import RequestException

from config import Config
from domain.models import PlcStatus, Reading, TwinState

logger = logging.getLogger(__name__)

FLUSH_INTERVAL_S = 1.0
RETRY_MIN_S = 1.0
RETRY_MAX_S = 30.0
MAX_BUFFER_POINTS = 50000
WRITE_TIMEOUT_S = 5
# Latido para el healthcheck de Docker: el hilo de escritura sigue vivo
HEARTBEAT_FILE = Path("/tmp/heartbeat")


class InfluxWriter:
    def __init__(self, config: Config) -> None:
        self._client = InfluxDBClient(
            host=config.influx_host,
            port=config.influx_port,
            username=config.influx_user,
            password=config.influx_password,
            database=config.influx_db,
            timeout=WRITE_TIMEOUT_S,   # sin timeout una escritura colgada bloquearia el hilo para siempre
            retries=1,
        )
        self._buffer: deque[dict] = deque(maxlen=MAX_BUFFER_POINTS)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._retry_s = RETRY_MIN_S

    def add_reading(self, reading: Reading) -> None:
        if reading.ts <= 0:
            logger.warning("Lectura con ts invalido descartada: %s/%s ts=%s", reading.plc, reading.variable, reading.ts)
            return
        point = {
            "measurement": "sensor_readings",
            "tags": {"plc": reading.plc, "variable": reading.variable},
            "fields": {"value": reading.value},
            "time": reading.ts * 1_000_000_000,
        }
        with self._lock:
            self._buffer.append(point)

    def add_status(self, status: PlcStatus) -> None:
        if status.ts <= 0:
            logger.warning("Status con ts invalido descartado: %s ts=%s", status.plc, status.ts)
            return
        point = {
            "measurement": "plc_status",
            "tags": {"plc": status.plc},
            "fields": {"online": 1 if status.online else 0},
            "time": status.ts * 1_000_000_000,
        }
        with self._lock:
            self._buffer.append(point)

    def add_twin_state(self, state: TwinState) -> None:
        if state.ts <= 0:
            logger.warning("Estado del gemelo con ts invalido descartado: %s ts=%s", state.plc, state.ts)
            return
        point = {
            "measurement": "twin_state",
            "tags": {"plc": state.plc},
            "fields": {
                "level_real": float(state.level_real),
                "level_model": float(state.level_model),
                "deviation": float(state.deviation),
                "leak_lpm": float(state.leak_lpm),
                "threshold": float(state.threshold),
                "alarmed": 1 if state.alarmed else 0,
            },
            "time": state.ts * 1_000_000_000,
        }
        with self._lock:
            self._buffer.append(point)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="influx-flusher", daemon=True)
        self._thread.start()

    def _drain(self) -> list[dict]:
        with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()
        return batch

    def _requeue(self, batch: list[dict]) -> None:
        with self._lock:
            dropped = max(0, len(self._buffer) + len(batch) - self._buffer.maxlen)
            self._buffer.extendleft(reversed(batch))
        if dropped:
            logger.warning("Cola llena: %d puntos antiguos descartados", dropped)

    def _flush(self) -> bool:
        """Escribe el buffer pendiente. Devuelve False si InfluxDB no esta disponible (lote reencolado)."""
        batch = self._drain()
        if not batch:
            return True
        try:
            self._client.write_points(batch, time_precision="n")
            self._retry_s = RETRY_MIN_S
        except InfluxDBClientError as exc:
            logger.warning("InfluxDB rechazo el lote (4xx: %s); lote descartado (%d puntos)", exc, len(batch))
            self._retry_s = RETRY_MIN_S
        except (InfluxDBServerError, RequestException, OSError) as exc:
            self._requeue(batch)
            logger.warning("InfluxDB no disponible (%s); reintento en %.0f s (%d puntos en cola)",
                           exc, self._retry_s, len(self._buffer))
            return False
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            HEARTBEAT_FILE.touch()
            if not self._flush():
                self._stop.wait(self._retry_s)
                self._retry_s = min(self._retry_s * 2, RETRY_MAX_S)
                continue
            self._stop.wait(FLUSH_INTERVAL_S)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=WRITE_TIMEOUT_S + 2)
        # vaciado final: los puntos recibidos antes de la senal de parada no se pierden
        pending = len(self._buffer)
        if pending and self._flush():
            logger.info("Buffer vaciado al parar: %d puntos escritos", pending)
        elif pending:
            logger.warning("Parada con InfluxDB no disponible: %d puntos sin escribir", len(self._buffer))
