from config import (
    MA_MAX,
    MA_MIN,
    MA_REGISTER_MAX,
    MA_REGISTER_SCALE,
    PCT_RANGE,
)

def engineering_to_ma(value: float, span: tuple[float, float]) -> float:
    low, high = span
    ratio = (value - low) / (high - low)
    return MA_MIN + _clamp(ratio, 0.0, 1.0) * (MA_MAX - MA_MIN)


def ma_to_engineering(ma: float, span: tuple[float, float]) -> float:
    low, high = span
    ratio = (ma - MA_MIN) / (MA_MAX - MA_MIN)
    return low + _clamp(ratio, 0.0, 1.0) * (high - low)


def ma_to_register(ma: float) -> int:
    return int(round(_clamp(ma, 0.0, MA_REGISTER_MAX) * MA_REGISTER_SCALE))


def register_to_ma(register: int) -> float:
    return register / MA_REGISTER_SCALE


def percent_to_register(percent: float) -> int:
    return int(round(_clamp(percent, *PCT_RANGE)))


def register_to_percent(register: int) -> float:
    return _clamp(float(register), *PCT_RANGE)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
