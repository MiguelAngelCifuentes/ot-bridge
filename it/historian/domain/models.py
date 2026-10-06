from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    plc: str
    variable: str
    value: int
    unit: str
    ts: int
    q: int = 1


@dataclass(frozen=True)
class TwinState:
    plc: str
    ts: int
    level_real: float
    level_model: float
    deviation: float
    leak_lpm: float
    threshold: float
    alarmed: bool


@dataclass(frozen=True)
class PlcStatus:
    plc: str
    online: bool
    ts: int
