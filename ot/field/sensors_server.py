import asyncio

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from config import (
    BIND_HOST,
    DEVICE_ID,
    FLOW_RANGE_LPM,
    LEVEL_RANGE_L,
    MA_CABLE_CUT,
    MA_SHORT_CIRCUIT,
    SENSOR_REG_EMERGENCY_STOP,
    SENSOR_REG_INLET_FLOW,
    SENSOR_REG_LEVEL,
    SENSOR_REG_OUTLET_FLOW,
    SENSOR_REG_PUMP_CONFIRMED,
    SENSOR_REG_PUMP_SPEED,
    SENSOR_REGISTER_COUNT,
    SENSORS_PORT,
)
from signal_conversion import (
    engineering_to_ma,
    ma_to_register,
    percent_to_register,
)
from tank_simulator import ProcessState

READ_INPUT_REGISTERS = 4


class SensorsServer:

    def __init__(self, host: str = BIND_HOST, port: int = SENSORS_PORT, device_id: int = DEVICE_ID):
        self._address = (host, port)
        self._device_id = device_id
        self._server: ModbusTcpServer | None = None

    async def start(self) -> None:
        device = SimDevice(
            id=self._device_id,
            simdata=(
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=1, values=0, datatype=DataType.REGISTERS, readonly=True)],
                [SimData(0, count=SENSOR_REGISTER_COUNT, values=0, datatype=DataType.REGISTERS)],
            ),
        )
        self._server = ModbusTcpServer(context=device, address=self._address)
        asyncio.create_task(self._server.serve_forever())

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

    async def update(self, state: ProcessState) -> None:
        if self._server is None:
            raise RuntimeError("SensorsServer.start() must be awaited before update()")

        await self._server.context.async_setValues(
            self._device_id, READ_INPUT_REGISTERS, 0, self._build_registers(state)
        )

    def _build_registers(self, state: ProcessState) -> list[int]:
        level_ma = level_signal_ma(state)

        registers = [0] * SENSOR_REGISTER_COUNT
        registers[SENSOR_REG_LEVEL] = ma_to_register(level_ma)
        registers[SENSOR_REG_INLET_FLOW] = ma_to_register(
            engineering_to_ma(state.inlet_flow_lpm, FLOW_RANGE_LPM)
        )
        registers[SENSOR_REG_OUTLET_FLOW] = ma_to_register(
            engineering_to_ma(state.outlet_flow_lpm, FLOW_RANGE_LPM)
        )
        registers[SENSOR_REG_PUMP_CONFIRMED] = int(state.pump_running_confirmed)
        registers[SENSOR_REG_EMERGENCY_STOP] = int(state.emergency_stop_pressed)
        registers[SENSOR_REG_PUMP_SPEED] = percent_to_register(state.pump_speed_pct)
        return registers


def level_signal_ma(state: ProcessState) -> float:
    if state.level_sensor_cable_cut:
        return MA_CABLE_CUT
    if state.level_sensor_short_circuit:
        return MA_SHORT_CIRCUIT
    return engineering_to_ma(state.level_l, LEVEL_RANGE_L)
