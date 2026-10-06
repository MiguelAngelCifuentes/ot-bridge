from dataclasses import dataclass

from config import (
    CONTACTOR_CONFIRM_DELAY_S,
    INITIAL_LEVEL_L,
    PUMP_MAX_FLOW_LPM,
    PUMP_MIN_SPEED_PCT,
    PUMP_SPEED_RAMP,
    TANK_CAPACITY_L,
    VALVE_FLOW_LEVEL_EXPONENT,
    VALVE_MAX_FLOW_LPM,
)


@dataclass
class ActuatorCommands:
    pump_run: bool = False
    pump_speed_setpoint_pct: float = 0.0
    valve_open: bool = False


@dataclass
class FaultInjection:
    pump_failed: bool = False
    level_sensor_cable_cut: bool = False
    level_sensor_short_circuit: bool = False
    contactor_no_confirm: bool = False
    emergency_stop_pressed: bool = False


@dataclass
class ProcessState:
    level_l: float
    inlet_flow_lpm: float
    outlet_flow_lpm: float
    overflow_flow_lpm: float
    pump_speed_pct: float
    pump_running_confirmed: bool
    emergency_stop_pressed: bool
    level_sensor_cable_cut: bool
    level_sensor_short_circuit: bool


class TankSimulator:

    def __init__(self, initial_level_l: float = INITIAL_LEVEL_L):
        self._level_l = initial_level_l
        self._pump_speed_pct = 0.0
        self._inlet_flow_lpm = 0.0
        self._outlet_flow_lpm = 0.0
        self._overflow_flow_lpm = 0.0
        self._contactor_confirm_timer_s = 0.0
        self._pump_running_confirmed = False

        self.commands = ActuatorCommands()
        self.faults = FaultInjection()

    def step(self, dt_s: float) -> None:
        self._update_pump_speed()
        self._update_contactor_feedback(dt_s)
        self._update_inlet_flow()
        self._update_outlet_flow()
        self._integrate_level(dt_s)

    def force_level(self, level_l: float) -> None:
        self._level_l = _clamp(level_l, 0.0, TANK_CAPACITY_L)

    def read_state(self) -> ProcessState:
        return ProcessState(
            level_l=self._level_l,
            inlet_flow_lpm=self._inlet_flow_lpm,
            outlet_flow_lpm=self._outlet_flow_lpm,
            overflow_flow_lpm=self._overflow_flow_lpm,
            pump_speed_pct=self._pump_speed_pct,
            pump_running_confirmed=self._pump_running_confirmed,
            emergency_stop_pressed=self.faults.emergency_stop_pressed,
            level_sensor_cable_cut=self.faults.level_sensor_cable_cut,
            level_sensor_short_circuit=self.faults.level_sensor_short_circuit,
        )

    def _pump_is_energized(self) -> bool:
        if self.faults.emergency_stop_pressed or self.faults.pump_failed:
            return False
        return self.commands.pump_run

    def _update_pump_speed(self) -> None:
        if self._pump_is_energized():
            target = _clamp(self.commands.pump_speed_setpoint_pct, 0.0, 100.0)
        else:
            target = 0.0

        self._pump_speed_pct += (target - self._pump_speed_pct) * PUMP_SPEED_RAMP
        self._pump_speed_pct = _clamp(self._pump_speed_pct, 0.0, 100.0)

    def _update_contactor_feedback(self, dt_s: float) -> None:
        if not self._pump_is_energized() or self.faults.contactor_no_confirm:
            self._contactor_confirm_timer_s = 0.0
            self._pump_running_confirmed = False
            return

        self._contactor_confirm_timer_s += dt_s
        self._pump_running_confirmed = (
            self._contactor_confirm_timer_s >= CONTACTOR_CONFIRM_DELAY_S
        )

    def _update_inlet_flow(self) -> None:
        if self._pump_speed_pct < PUMP_MIN_SPEED_PCT:
            self._inlet_flow_lpm = 0.0
            return

        self._inlet_flow_lpm = PUMP_MAX_FLOW_LPM * (self._pump_speed_pct / 100.0)

    def _update_outlet_flow(self) -> None:
        if not self.commands.valve_open or self._level_l <= 0.0:
            self._outlet_flow_lpm = 0.0
            return

        fill_ratio = self._level_l / TANK_CAPACITY_L
        self._outlet_flow_lpm = VALVE_MAX_FLOW_LPM * (fill_ratio ** VALVE_FLOW_LEVEL_EXPONENT)

    def _integrate_level(self, dt_s: float) -> None:
        net_flow_lpm = self._inlet_flow_lpm - self._outlet_flow_lpm
        self._level_l += net_flow_lpm * (dt_s / 60.0)

        if self._level_l > TANK_CAPACITY_L:
            excess_l = self._level_l - TANK_CAPACITY_L
            self._overflow_flow_lpm = excess_l * (60.0 / dt_s)
        else:
            self._overflow_flow_lpm = 0.0

        self._level_l = _clamp(self._level_l, 0.0, TANK_CAPACITY_L)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
