from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    variable: str
    value: int
    unit: str
    ts: int
    q: int = 1


@dataclass(frozen=True)
class PlcStatus:
    plc: str
    online: bool
    ts: int
