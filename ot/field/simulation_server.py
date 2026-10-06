import asyncio
from dataclasses import dataclass, field

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from config import (
    BIND_HOST,
    DEVICE_ID,
    SIM_HOLDING_COUNT,
    SIM_INPUT_COUNT,
    SIM_REG_ACTIVE_FAULTS,
    SIM_REG_CLEAR_FAULTS,
    SIM_REG_CMD_PUMP_RUN,
    SIM_REG_CMD_PUMP_SPEED_SETPOINT,
    SIM_REG_CMD_VALVE_OPEN,
    SIM_REG_FAULT_CABLE_CUT,
    SIM_REG_FAULT_CONTACTOR_NO_CONFIRM,
    SIM_REG_FAULT_EMERGENCY_STOP,
    SIM_REG_FAULT_PUMP_FAILED,
    SIM_REG_FAULT_SHORT_CIRCUIT,
    SIM_REG_FORCE_LEVEL_L,
    SIM_REG_FORCE_LEVEL_TRIGGER,
    SIM_REG_LEVEL_SIGNAL,
    SIM_REG_OVERFLOW_FLOW_X10,
    SIM_REG_PUMP_CONFIRMED,
    SIM_REG_REAL_INLET_FLOW_X10,
    SIM_REG_REAL_LEVEL_X10,
    SIM_REG_REAL_OUTLET_FLOW_X10,
    SIM_REG_REAL_PUMP_SPEED,
    SIM_REGISTER_MAX,
    SIMULATION_PORT,
)
from sensors_server import level_signal_ma
from signal_conversion import ma_to_register, percent_to_register
from tank_simulator import ActuatorCommands, FaultInjection, ProcessState

READ_HOLDING_REGISTERS = 3
READ_INPUT_REGISTERS = 4

FAULT_REGISTERS = {
    "pump_failed": SIM_REG_FAULT_PUMP_FAILED,
    "level_sensor_cable_cut": SIM_REG_FAULT_CABLE_CUT,
    "level_sensor_short_circuit": SIM_REG_FAULT_SHORT_CIRCUIT,
    "contactor_no_confirm": SIM_REG_FAULT_CONTACTOR_NO_CONFIRM,
    "emergency_stop_pressed": SIM_REG_FAULT_EMERGENCY_STOP,
}


@dataclass
class SimulationControls:
    faults: FaultInjection = field(default_factory=FaultInjection)
    clear_faults_requested: bool = False
    force_level_requested: bool = False
    force_level_l: float = 0.0


class SimulationServer:

    def __init__(self, host: str = BIND_HOST, port: int = SIMULATION_PORT, device_id: int = DEVICE_ID):
        self._address = (host, port)
        self._device_id = device_id
        self._server: ModbusTcpServer | None = None

    async def start(self) -> None:
        device = SimDevice(
            id=self._device_id,
            simdata=(
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=SIM_HOLDING_COUNT, values=0, datatype=DataType.REGISTERS)],
                [SimData(0, count=SIM_INPUT_COUNT, values=0, datatype=DataType.REGISTERS)],
            ),
        )
        self._server = ModbusTcpServer(context=device, address=self._address)
        asyncio.create_task(self._server.serve_forever())

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

    async def read_controls(self) -> SimulationControls:
        registers = await self._context().async_getValues(
            self._device_id, READ_HOLDING_REGISTERS, 0, SIM_HOLDING_COUNT
        )
        faults = FaultInjection(
            **{name: bool(registers[offset]) for name, offset in FAULT_REGISTERS.items()}
        )
        return SimulationControls(
            faults=faults,
            clear_faults_requested=bool(registers[SIM_REG_CLEAR_FAULTS]),
            force_level_requested=bool(registers[SIM_REG_FORCE_LEVEL_TRIGGER]),
            force_level_l=float(registers[SIM_REG_FORCE_LEVEL_L]),
        )

    async def toggle_fault(self, name: str) -> None:
        offset = FAULT_REGISTERS[name]
        current = await self._context().async_getValues(
            self._device_id, READ_HOLDING_REGISTERS, offset, 1
        )
        await self._write_holding(offset, [0 if current[0] else 1])

    async def clear_faults(self) -> None:
        await self._write_holding(0, [0] * (SIM_REG_CLEAR_FAULTS + 1))

    async def acknowledge_force_level(self) -> None:
        await self._write_holding(SIM_REG_FORCE_LEVEL_TRIGGER, [0])

    async def publish(self, state: ProcessState, commands: ActuatorCommands, faults: FaultInjection) -> None:
        await self._context().async_setValues(
            self._device_id, READ_INPUT_REGISTERS, 0, _build_registers(state, commands, faults)
        )

    async def _write_holding(self, offset: int, values: list[int]) -> None:
        await self._context().async_setValues(
            self._device_id, READ_HOLDING_REGISTERS, offset, values
        )

    def _context(self):
        if self._server is None:
            raise RuntimeError("SimulationServer.start() must be awaited first")
        return self._server.context


def _build_registers(state: ProcessState, commands: ActuatorCommands, faults: FaultInjection) -> list[int]:
    registers = [0] * SIM_INPUT_COUNT
    registers[SIM_REG_REAL_LEVEL_X10] = _tenths(state.level_l)
    registers[SIM_REG_REAL_INLET_FLOW_X10] = _tenths(state.inlet_flow_lpm)
    registers[SIM_REG_REAL_OUTLET_FLOW_X10] = _tenths(state.outlet_flow_lpm)
    registers[SIM_REG_OVERFLOW_FLOW_X10] = _tenths(state.overflow_flow_lpm)
    registers[SIM_REG_REAL_PUMP_SPEED] = percent_to_register(state.pump_speed_pct)
    registers[SIM_REG_PUMP_CONFIRMED] = int(state.pump_running_confirmed)
    registers[SIM_REG_CMD_PUMP_RUN] = int(commands.pump_run)
    registers[SIM_REG_CMD_PUMP_SPEED_SETPOINT] = percent_to_register(commands.pump_speed_setpoint_pct)
    registers[SIM_REG_CMD_VALVE_OPEN] = int(commands.valve_open)
    registers[SIM_REG_ACTIVE_FAULTS] = _fault_bitmask(faults)
    registers[SIM_REG_LEVEL_SIGNAL] = ma_to_register(level_signal_ma(state))
    return registers


def _fault_bitmask(faults: FaultInjection) -> int:
    return sum(
        1 << offset for name, offset in FAULT_REGISTERS.items() if getattr(faults, name)
    )


def _tenths(value: float) -> int:
    return int(round(max(0.0, min(value * 10.0, SIM_REGISTER_MAX))))
