from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from adapters.api_client import ApiClient
from adapters.mqtt_io import MqttIo
from adapters.state_store import StateStore
from domain.engine import AlarmEngine, Sample
from domain.rules import COMM_RULE, DEFAULT_RULES, Rule

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = Path("/tmp/heartbeat")      # healthcheck: el bucle de reglas sigue vivo


class AlarmService:
    def __init__(self, mqtt: MqttIo, api: ApiClient, poll_interval_s: int, store: StateStore) -> None:
        self._mqtt = mqtt
        self._api = api
        self._poll_interval_s = poll_interval_s
        self._store = store
        self._engine = AlarmEngine()
        self._rules: tuple[Rule, ...] = DEFAULT_RULES
        self._rules_lock = threading.Lock()
        self._stop = threading.Event()

    def start(self) -> None:
        self._engine.load_states(self._store.load())
        thread = threading.Thread(target=self._refresh_rules, name="rules-refresh", daemon=True)
        thread.start()

    def _refresh_rules(self) -> None:
        last_count = None
        while not self._stop.is_set():
            HEARTBEAT_FILE.touch()
            rules = self._api.fetch_rules()
            if rules is not None:
                with self._rules_lock:
                    self._rules = rules
                    events = self._engine.reconcile(rules)
                self._publish_events(events)
                if len(rules) != last_count:
                    logger.info("Reglas cargadas desde la API: %d reglas", len(rules))
                    last_count = len(rules)
            self._reconcile_with_api()
            self._stop.wait(self._poll_interval_s)

    @staticmethod
    def _owned(code: str) -> bool:
        """Codigos de alarma que gestiona este motor (las del gemelo digital las gestiona el gemelo)."""
        return code == COMM_RULE.key or code.startswith("th") or code.startswith("estado:bit")

    def _reconcile_with_api(self) -> None:
        """Autorreparacion: si se perdio un evento (reinicio del broker o de la API), el estado de la API se
        alinea con el del motor, que es la referencia para sus propias alarmas."""
        open_alarms = self._api.fetch_open_alarms()
        if open_alarms is None:
            return
        in_api = {(a["machineName"], a["code"]): a for a in open_alarms if self._owned(a.get("code") or "")}
        with self._rules_lock:
            active = self._engine.active_items()
        missing = [(plc, rule, "ACTIVE", rule.message) for (plc, code), rule in active.items() if (plc, code) not in in_api]
        stale = [(plc, Rule(a["variable"], "eq", 0.0, a["severity"], a["message"] or "", code=code), "RESOLVED",
                  a["message"] or "") for (plc, code), a in in_api.items() if (plc, code) not in active]
        if missing or stale:
            logger.warning("Reconciliacion con la API: %d alarmas reenviadas, %d cerradas", len(missing), len(stale))
            self._publish_events(missing + stale)

    def _publish_events(self, events) -> None:
        for plc, rule, state, message in events:
            self._mqtt.publish_event(plc, rule.variable, rule.severity, state, message, rule.key)
        if events:
            self._persist()

    def _persist(self) -> None:
        self._store.save(self._engine.dump_states())

    def handle_status(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
            plc = str(data["plc"])
            online = bool(data["online"])
        except (ValueError, KeyError, TypeError):
            logger.warning("Status malformado en %s; descartado", topic)
            return
        if not online:
            with self._rules_lock:
                events = self._engine.comm_lost(plc)
            self._publish_events(events)

    def handle_telemetry(self, topic: str, payload: bytes) -> None:
        if "/telemetry/" not in topic:
            return
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            logger.warning("Payload malformado en %s; descartado", topic)
            return
        try:
            sample = Sample(
                plc=str(data["plc"]),
                variable=str(data["variable"]),
                value=float(data["value"]),
                ts=int(data["ts"]),
            )
            q = int(data.get("q", 1))
        except (KeyError, TypeError, ValueError):
            logger.warning("Campos invalidos en %s; descartado", topic)
            return

        with self._rules_lock:
            if q != 1:
                events = self._engine.comm_lost(sample.plc)        # lectura no valida: sin datos fiables
            else:
                events = self._engine.comm_restored(sample.plc) + self._engine.evaluate(sample, self._rules)
        self._publish_events(events)

    def stop(self) -> None:
        self._stop.set()
        self._persist()
