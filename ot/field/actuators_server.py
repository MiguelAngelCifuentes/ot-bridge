import asyncio

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from config import (
    ACTUATOR_REG_PUMP_RUN,
    ACTUATOR_REG_PUMP_SPEED_SETPOINT,
    ACTUATOR_REG_VALVE_OPEN,
    ACTUATOR_REGISTER_COUNT,
    ACTUATORS_PORT,
    BIND_HOST,
    DEVICE_ID,
)
from signal_conversion import register_to_percent
from tank_simulator import ActuatorCommands

READ_HOLDING_REGISTERS = 3


class ActuatorsServer:

    def __init__(self, host: str = BIND_HOST, port: int = ACTUATORS_PORT, device_id: int = DEVICE_ID):
        self._address = (host, port)
        self._device_id = device_id
        self._server: ModbusTcpServer | None = None

    async def start(self) -> None:
        device = SimDevice(
            id=self._device_id,
            simdata=(
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=1, values=False, datatype=DataType.BITS, readonly=True)],
                [SimData(0, count=ACTUATOR_REGISTER_COUNT, values=0, datatype=DataType.REGISTERS)],
                [SimData(0, count=1, values=0, datatype=DataType.REGISTERS, readonly=True)],
            ),
        )
        self._server = ModbusTcpServer(context=device, address=self._address)
        asyncio.create_task(self._server.serve_forever())

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

    async def read_commands(self) -> ActuatorCommands:
        if self._server is None:
            raise RuntimeError("ActuatorsServer.start() must be awaited before read_commands()")

        registers = await self._server.context.async_getValues(
            self._device_id, READ_HOLDING_REGISTERS, 0, ACTUATOR_REGISTER_COUNT
        )
        return ActuatorCommands(
            pump_run=bool(registers[ACTUATOR_REG_PUMP_RUN]),
            pump_speed_setpoint_pct=register_to_percent(registers[ACTUATOR_REG_PUMP_SPEED_SETPOINT]),
            valve_open=bool(registers[ACTUATOR_REG_VALVE_OPEN]),
        )
