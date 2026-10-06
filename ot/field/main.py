import argparse
import asyncio
import contextlib
import sys

from actuators_server import ActuatorsServer
from config import SCAN_INTERVAL_S
from sensors_server import SensorsServer
from simulation_server import SimulationServer
from tank_simulator import TankSimulator

FAULT_KEYS = {
    "1": "pump_failed",
    "2": "level_sensor_cable_cut",
    "3": "level_sensor_short_circuit",
    "4": "contactor_no_confirm",
    "5": "emergency_stop_pressed",
}
CLEAR_FAULTS_KEY = "0"

BANNER = """OT-Bridge field simulator
  sensors    Modbus TCP :5020  (input registers, read only)
  actuators  Modbus TCP :5021  (holding registers, read write)
  simulation Modbus TCP :5022  (fault injection + physical truth, used by FUXA)

  1 pump failure           2 level sensor cable cut
  3 level sensor short     4 contactor no confirm
  5 emergency stop         0 clear all faults
  q quit
"""

# Headless mode (no console, e.g. inside the field-simulator container): faults are injected only
# through :5022 (FUXA "Simulador" tab) and the status line is logged every HEADLESS_STATUS_EVERY_S.
HEADLESS_STATUS_EVERY_S = 10.0


async def run(headless: bool = False) -> None:
    simulator = TankSimulator()
    sensors = SensorsServer()
    actuators = ActuatorsServer()
    simulation = SimulationServer()

    await sensors.start()
    await actuators.start()
    await simulation.start()
    print(BANNER.split("\n\n")[0] + "\n  headless: faults via :5022 only" if headless else BANNER, flush=True)

    keyboard = asyncio.create_task(asyncio.Event().wait() if headless else _handle_keyboard(simulation))
    status_every = max(1, round(HEADLESS_STATUS_EVERY_S / SCAN_INTERVAL_S)) if headless else 1
    cycle = 0
    try:
        while not keyboard.done():
            await _apply_simulation_controls(simulator, simulation)
            simulator.commands = await actuators.read_commands()
            simulator.step(SCAN_INTERVAL_S)
            state = simulator.read_state()
            await sensors.update(state)
            await simulation.publish(state, simulator.commands, simulator.faults)
            if cycle % status_every == 0:
                _print_status(simulator, state)
            cycle += 1
            await asyncio.sleep(SCAN_INTERVAL_S)
    finally:
        keyboard.cancel()
        await sensors.stop()
        await actuators.stop()
        await simulation.stop()


async def _apply_simulation_controls(simulator: TankSimulator, simulation: SimulationServer) -> None:
    controls = await simulation.read_controls()
    if controls.clear_faults_requested:
        await simulation.clear_faults()
        controls = await simulation.read_controls()
    if controls.force_level_requested:
        simulator.force_level(controls.force_level_l)
        await simulation.acknowledge_force_level()
    simulator.faults = controls.faults


async def _handle_keyboard(simulation: SimulationServer) -> None:
    while True:
        key = (await asyncio.to_thread(sys.stdin.readline)).strip().lower()
        if key == "q" or not key:
            return
        if key in FAULT_KEYS:
            await simulation.toggle_fault(FAULT_KEYS[key])
        elif key == CLEAR_FAULTS_KEY:
            await simulation.clear_faults()


def _print_status(simulator: TankSimulator, state) -> None:
    active = [name for name in FAULT_KEYS.values() if getattr(simulator.faults, name)]
    print(
        f"level {state.level_l:7.1f} L | "
        f"in {state.inlet_flow_lpm:6.1f} | out {state.outlet_flow_lpm:6.1f} | "
        f"overflow {state.overflow_flow_lpm:6.1f} lpm | "
        f"pump {state.pump_speed_pct:5.1f} % | "
        f"confirmed {int(state.pump_running_confirmed)} | "
        f"faults {','.join(active) if active else '-'}",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OT-Bridge field simulator")
    parser.add_argument("--headless", action="store_true", help="run without console (no keyboard input)")
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(headless=args.headless))
