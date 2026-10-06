from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


class StateStore:
    """Persistencia en disco de las alarmas activas (sobrevive a reinicios del motor)."""

    def __init__(self, path: str) -> None:
        self._path = path

    def load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except Exception as exc:
            logger.warning("No se pudo leer el estado persistido (%s); se arranca limpio", exc)
            return {}

    def save(self, data: dict) -> None:
        try:
            directory = os.path.dirname(self._path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("No se pudo guardar el estado persistido (%s)", exc)
