from __future__ import annotations

import json
import logging
import urllib.request

from domain.rules import Rule

logger = logging.getLogger(__name__)


class ApiClient:
    """Consulta las reglas de umbral a la API (GET /api/thresholds?enabledOnly=true).
    Si la API no responde devuelve None (el servicio mantiene las reglas actuales)."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def fetch_open_alarms(self) -> list[dict] | None:
        """Alarmas abiertas (ACTIVE y ACKNOWLEDGED) registradas en la API, o None si no responde."""
        alarms = []
        try:
            for state in ("ACTIVE", "ACKNOWLEDGED"):
                url = f"{self._base_url}/api/alarms?state={state}&size=200"
                request = urllib.request.Request(url, headers={"X-API-Key": self._api_key} if self._api_key else {})
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    alarms += json.loads(response.read().decode("utf-8"))["content"]
            return alarms
        except Exception as exc:
            logger.warning("API no disponible para reconciliar alarmas (%s)", exc)
            return None

    def fetch_rules(self) -> tuple[Rule, ...] | None:
        url = f"{self._base_url}/api/thresholds?enabledOnly=true"
        request = urllib.request.Request(url, headers={"X-API-Key": self._api_key} if self._api_key else {})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
            rules = tuple(
                Rule(
                    variable=str(item["variable"]),
                    op=str(item["operator"]),
                    value=float(item["value"]),
                    severity=str(item["severity"]),
                    message=str(item.get("message") or ""),
                    code=f"th{item['id']}",
                    deadband=float(item.get("deadband") or 0.0),
                    delay_s=int(item.get("delaySeconds") or 0),
                )
                for item in data
            )
            return rules
        except Exception as exc:
            logger.warning("API no disponible (%s); se mantienen las reglas actuales", exc)
            return None
