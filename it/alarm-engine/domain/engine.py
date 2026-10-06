from __future__ import annotations

import logging
from dataclasses import dataclass

from domain.rules import COMM_RULE, Rule

logger = logging.getLogger(__name__)

Event = tuple[str, Rule, str, str]      # (plc, regla, ACTIVE|RESOLVED, mensaje)


@dataclass(frozen=True)
class Sample:
    plc: str
    variable: str
    value: float
    ts: int


class AlarmEngine:
    """Maquina de estados por (plc, codigo de regla), con retardo y histeresis (ISA-18.2).

    - ACTIVE cuando la condicion se mantiene `delay_s` segundos (medidos con el ts del dato).
    - RESOLVED cuando la condicion desaparece (con histeresis `deadband`) durante `delay_s`.
    - Si una regla activa desaparece de la configuracion, su alarma se resuelve.
    - Perdida de comunicacion: alarma propia CRITICAL; las demas se congelan (ni se activan ni se
      resuelven) porque sin datos su estado real es desconocido.
    """

    def __init__(self) -> None:
        self._active: dict[tuple[str, str], Rule] = {}
        self._pending: dict[tuple[str, str], int] = {}   # desde cuando se cumple el cambio pendiente
        self._comm_lost: set[str] = set()

    # ------------------------------------------------------------------ evaluacion
    def evaluate(self, sample: Sample, rules: tuple[Rule, ...]) -> list[Event]:
        if sample.plc in self._comm_lost:
            return []                                    # datos congelados hasta recuperar comunicacion
        events: list[Event] = []
        for rule in rules:
            if rule.variable != sample.variable:
                continue
            key = (sample.plc, rule.key)
            active = key in self._active
            changing = (not active and rule.compare(sample.value)) or (active and rule.cleared(sample.value))
            if not changing:
                self._pending.pop(key, None)
                continue
            since = self._pending.setdefault(key, sample.ts)
            if sample.ts - since < rule.delay_s:
                continue
            self._pending.pop(key, None)
            if active:
                self._active.pop(key)
                logger.info("RESOLVED: %s/%s -> %s", sample.plc, rule.key, sample.value)
                events.append((sample.plc, rule, "RESOLVED", rule.message))
            else:
                self._active[key] = rule
                logger.info("ACTIVE: %s/%s -> %s", sample.plc, rule.key, sample.value)
                events.append((sample.plc, rule, "ACTIVE", rule.message))
        return events

    def reconcile(self, rules: tuple[Rule, ...]) -> list[Event]:
        """Resuelve las alarmas activas cuya regla ya no existe (desactivada o borrada)."""
        current = {rule.key for rule in rules} | {COMM_RULE.key}
        events: list[Event] = []
        for key in [k for k in self._active if k[1] not in current]:
            rule = self._active.pop(key)
            self._pending.pop(key, None)
            logger.info("RESOLVED (regla retirada): %s/%s", key[0], key[1])
            events.append((key[0], rule, "RESOLVED", rule.message + " (regla retirada)"))
        return events

    # ------------------------------------------------------------------ comunicacion
    def comm_lost(self, plc: str) -> list[Event]:
        if plc in self._comm_lost:
            return []
        self._comm_lost.add(plc)
        self._pending = {k: v for k, v in self._pending.items() if k[0] != plc}
        self._active[(plc, COMM_RULE.key)] = COMM_RULE
        logger.warning("Comunicacion con %s perdida: alarma activa y resto de alarmas congeladas", plc)
        return [(plc, COMM_RULE, "ACTIVE", COMM_RULE.message)]

    def comm_restored(self, plc: str) -> list[Event]:
        if plc not in self._comm_lost:
            return []
        self._comm_lost.discard(plc)
        self._active.pop((plc, COMM_RULE.key), None)
        logger.info("Comunicacion con %s recuperada", plc)
        return [(plc, COMM_RULE, "RESOLVED", COMM_RULE.message)]

    def is_comm_lost(self, plc: str) -> bool:
        return plc in self._comm_lost

    def active_items(self) -> dict[tuple[str, str], Rule]:
        return dict(self._active)

    # ------------------------------------------------------------------ persistencia
    def dump_states(self) -> dict:
        return {"active": {f"{plc}|{code}": _rule_to_dict(rule) for (plc, code), rule in self._active.items()},
                "comm_lost": sorted(self._comm_lost)}

    def load_states(self, data: dict) -> None:
        active = data.get("active", data) if isinstance(data, dict) else {}
        for key, item in active.items():
            if key == "comm_lost":
                continue
            try:
                plc, code = key.split("|", 1)
                self._active[(plc, code)] = Rule(**{k: item[k] for k in ("variable", "op", "value", "severity",
                                                                          "message")},
                                                 code=item.get("code", ""), deadband=item.get("deadband", 0.0),
                                                 delay_s=item.get("delay_s", 0))
            except (ValueError, KeyError, TypeError):
                logger.warning("Estado persistido invalido descartado: %s", key)
        self._comm_lost = set(data.get("comm_lost", [])) if isinstance(data, dict) else set()


def _rule_to_dict(rule: Rule) -> dict:
    return {"variable": rule.variable, "op": rule.op, "value": rule.value, "severity": rule.severity,
            "message": rule.message, "code": rule.code, "deadband": rule.deadband, "delay_s": rule.delay_s}
