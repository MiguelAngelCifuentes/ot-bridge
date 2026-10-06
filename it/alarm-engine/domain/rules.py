from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    """Regla de alarma. `code` identifica la alarma de forma unica: dos reglas CRITICAL sobre bits
    distintos de `estado` son alarmas distintas (antes colapsaban en una por (variable, severidad))."""

    variable: str
    op: str
    value: float
    severity: str
    message: str
    code: str = ""
    deadband: float = 0.0     # histeresis para resolver (unidades de la variable); no aplica a bits
    delay_s: int = 0          # la condicion debe mantenerse este tiempo para activar y para resolver

    @property
    def key(self) -> str:
        return self.code or f"{self.variable}:{self.op}:{self.value:g}"

    def compare(self, sample_value) -> bool:
        """¿Se cumple la condicion de alarma?"""
        try:
            v = float(sample_value)
        except (TypeError, ValueError):
            return False
        if self.op == "lt":
            return v < self.value
        if self.op == "le":
            return v <= self.value
        if self.op == "gt":
            return v > self.value
        if self.op == "ge":
            return v >= self.value
        if self.op == "eq":
            return v == self.value
        if self.op == "bit":
            return (int(v) & int(self.value)) != 0
        return False

    def cleared(self, sample_value) -> bool:
        """¿Ha desaparecido la condicion con la histeresis aplicada? (activa en lt/gt hasta salir de la banda)."""
        try:
            v = float(sample_value)
        except (TypeError, ValueError):
            return False
        if self.op in ("lt", "le"):
            return v >= self.value + self.deadband
        if self.op in ("gt", "ge"):
            return v <= self.value - self.deadband
        return not self.compare(v)


# Reglas de respaldo si la API no responde: los bits del registro de estado del PLC (fuente de verdad).
DEFAULT_RULES = (
    Rule("estado", "bit", 2.0, "critical", "Seta de emergencia", code="estado:bit2"),
    Rule("estado", "bit", 4.0, "critical", "Fallo sensor de nivel", code="estado:bit4"),
    Rule("estado", "bit", 8.0, "critical", "Fallo de arranque P-101", code="estado:bit8", delay_s=1),
    Rule("estado", "bit", 16.0, "high", "Nivel muy alto (>= 950 L)", code="estado:bit16", delay_s=2),
    Rule("estado", "bit", 32.0, "high", "Nivel muy bajo (<= 100 L)", code="estado:bit32", delay_s=2),
)

# Alarma propia de perdida de comunicacion con el PLC (no configurable: siempre existe)
COMM_RULE = Rule("comunicacion", "eq", 0.0, "critical", "Comunicacion con el PLC perdida", code="comunicacion")
