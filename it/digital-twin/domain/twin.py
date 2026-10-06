from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Si pasan mas de RESYNC_GAP_S sin lectura de nivel (datos a 1 Hz: hueco = perdida de comunicacion), el modelo
# se reinicia al valor real: integrar el hueco con los ultimos caudales conocidos (obsoletos) falsea el balance
RESYNC_GAP_S = 10.0
# Histeresis: la alarma se resuelve cuando la desviacion baja de umbral * RESOLVE_RATIO
RESOLVE_RATIO = 0.5


@dataclass(frozen=True)
class TwinState:
    """Estado del gemelo tras cada lectura de nivel (lo que se publica y se historiza)."""

    ts: int
    level_real: float
    level_model: float
    deviation: float
    leak_lpm: float
    threshold: float
    alarmed: bool


@dataclass(frozen=True)
class TwinUpdate:
    state: TwinState
    event: str | None  # "ACTIVE" | "RESOLVED" | None
    message: str | None


class MassBalanceTwin:
    """Gemelo de balance de masas con correccion proporcional (observador de Luenberger).

    Prediccion:  nivel_modelo += (ent - sal) / flow_divisor * dt / 60      (caudales en l/min x10)
    Correccion:  nivel_modelo += gain * (real - modelo) * dt

    La correccion absorbe los sesgos lentos (ruido, redondeos) para que el modelo no derive;
    una perdida no contabilizada sostenida mantiene un residuo estable proporcional a su
    caudal, que se estima (en l/min reales) como leak_lpm = 60 * gain * (modelo - real).
    """

    def __init__(self, threshold_l: float, gain: float, flow_divisor: float) -> None:
        self._threshold = threshold_l
        self._gain = gain
        self._flow_divisor = flow_divisor
        self._initialized = False
        self._model_l = 0.0
        self._last_ts = 0
        self._ent_lpm = 0.0
        self._sal_lpm = 0.0
        self._alarmed = False

    def update(self, variable: str, value: float, ts: int) -> TwinUpdate | None:
        """Procesa una lectura; devuelve el estado del gemelo solo en lecturas de nivel."""
        if variable == "caudal_ent":
            self._ent_lpm = value
            return None
        if variable == "caudal_sal":
            self._sal_lpm = value
            return None
        if variable != "nivel_x10":
            return None

        real_l = value / 10.0
        dt_s = float(ts - self._last_ts)
        if not self._initialized or dt_s > RESYNC_GAP_S or dt_s < 0:
            self._model_l = real_l
            self._last_ts = ts
            self._initialized = True
            return TwinUpdate(self._state(ts, real_l), None, None)

        self._last_ts = ts
        self._model_l += (self._ent_lpm - self._sal_lpm) / self._flow_divisor * dt_s / 60.0
        residual = real_l - self._model_l
        self._model_l += min(self._gain * dt_s, 1.0) * residual

        deviation = abs(real_l - self._model_l)
        event = message = None
        if not self._alarmed and deviation > self._threshold:
            self._alarmed = True
            event = "ACTIVE"
            message = f"Posible fuga o anomalia: desviacion de {deviation:.0f} L"
            logger.warning("DESVIACION: real=%.1f L modelo=%.1f L (%.1f L)", real_l, self._model_l, deviation)
        elif self._alarmed and deviation < self._threshold * RESOLVE_RATIO:
            self._alarmed = False
            event = "RESOLVED"
            message = "Desviacion corregida"
            logger.info("Desviacion corregida: real=%.1f L modelo=%.1f L", real_l, self._model_l)

        return TwinUpdate(self._state(ts, real_l), event, message)

    def _state(self, ts: int, real_l: float) -> TwinState:
        leak = 60.0 * self._gain * (self._model_l - real_l)
        return TwinState(
            ts=ts,
            level_real=round(real_l, 2),
            level_model=round(self._model_l, 2),
            deviation=round(real_l - self._model_l, 2),
            leak_lpm=round(leak, 2),
            threshold=self._threshold,
            alarmed=self._alarmed,
        )
