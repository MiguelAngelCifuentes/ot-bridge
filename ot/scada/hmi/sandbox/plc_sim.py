"""Simulador Modbus del PLC de la balsa para el sandbox de FUXA (solo pruebas, nunca el PLC real).

Porta el programa ot/plc/pous/programs/main.st (mismos registros %MW, setpoints, temporizadores TON de 3 s,
reset por pulso, arranque sin salto al pasar a manual y seta SCADA) y le añade una dinamica simple
del deposito para que el HMI se pueda probar de extremo a extremo.

Mapa (holding registers, direccion 0-based; FUXA usa 1-based = +1):
    MW100..MW105  1124..1129  hmi_nivel_x10, hmi_nivel_ma, hmi_caudal_ent, hmi_caudal_sal, hmi_velocidad, hmi_estado
    MW106..MW111  1130..1135  modo_manual, mando_marcha, mando_valvula, reset_fallos, velocidad_manual, seta_scada
Registros de inyeccion de fallos (solo simulador):
    2000  1 = el contactor no confirma la marcha (provoca fallo de arranque)
    2001  1 = transmisor de nivel fuera de rango (fallo de sensor)
    2002  1 = seta fisica pulsada
    2003  factor de aceleracion de la dinamica del deposito (0/1 = tiempo real)

Uso:  python ot/scada/hmi/sandbox/plc_sim.py [--port 5502] [--level 500]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
from dataclasses import dataclass, field

from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

log = logging.getLogger("plc-sim")

SCAN_S = 0.1
MW = 1024                       # %MW100 -> 1124: el buffer %QW ocupa 0..1023
HR_NIVEL, HR_MA, HR_ENT, HR_SAL, HR_VEL, HR_ESTADO = (MW + 100 + i for i in range(6))
HR_MODO, HR_MARCHA, HR_VALVULA, HR_RESET, HR_CONSIGNA, HR_SETA_SCADA = (MW + 106 + i for i in range(6))
SIM_NO_CONFIRM, SIM_SENSOR_FAIL, SIM_SETA_FISICA, SIM_SPEED = 2000, 2001, 2002, 2003

# Constantes del programa PLC
SP_ARRANQUE_BOMBA, SP_RESERVA, SP_REARME_CONSUMO = 300.0, 200.0, 250.0
SP_LLENO, SP_ALARMA_ALTA, SP_ALARMA_BAJA = 900.0, 950.0, 100.0
MA_MIN_VALIDO, MA_MAX_VALIDO, VELOCIDAD_AUTO = 350, 2050, 75

# Dinamica del proceso (ajustada a lo observado en la planta real)
LPM_POR_PCT = 1.2               # caudal de llenado por % de velocidad (75 % -> 90 l/min)
K_DESCARGA = 2.95               # salida por gravedad: q = k * sqrt(nivel)  (~78 l/min a 700 L)


@dataclass
class Ton:
    """Temporizador a la conexion IEC 61131-3."""
    pt: float
    elapsed: float = 0.0
    q: bool = False

    def __call__(self, inp: bool, dt: float) -> bool:
        self.elapsed = self.elapsed + dt if inp else 0.0
        self.q = inp and self.elapsed >= self.pt
        return self.q


@dataclass
class Plc:
    # memoria retenida entre ciclos
    en_reserva: bool = False
    bomba_auto_marcha: bool = False
    fallo_arranque: bool = False
    prev_modo: int = 0
    ton_arranque: Ton = field(default_factory=lambda: Ton(3.0))
    ton_paro: Ton = field(default_factory=lambda: Ton(3.0))
    # salidas %QW
    bomba_marcha: int = 0
    bomba_velo: int = 0
    valvula_abrir: int = 0

    def scan(self, io: dict, mw: dict, dt: float) -> None:
        """Un ciclo del programa .st. io = entradas %IW; mw = memoria %MW (se modifica in situ)."""
        seta_activa = io["seta_pulsada"] != 0 or mw["seta_scada"] != 0
        contactor_cerrado = io["confirmacion_marcha"] != 0
        nivel_litros = (io["nivel_ma_x100"] - 400.0) / 1600.0 * 1000.0
        caudal_ent = (io["caudal_entrada"] - 400.0) / 1600.0 * 150.0
        caudal_sal = (io["caudal_salida"] - 400.0) / 1600.0 * 150.0

        fallo_sensor = io["nivel_ma_x100"] < MA_MIN_VALIDO or io["nivel_ma_x100"] > MA_MAX_VALIDO
        alarma_alto = nivel_litros >= SP_ALARMA_ALTA and not fallo_sensor
        alarma_bajo = nivel_litros <= SP_ALARMA_BAJA and not fallo_sensor
        seguridades_ok = not seta_activa and not self.fallo_arranque and not fallo_sensor

        if nivel_litros <= SP_RESERVA:
            self.en_reserva = True
        if nivel_litros >= SP_REARME_CONSUMO:
            self.en_reserva = False
        consumo_permitido = not self.en_reserva and not fallo_sensor and not seta_activa

        if nivel_litros <= SP_ARRANQUE_BOMBA and not fallo_sensor:
            self.bomba_auto_marcha = True
        if nivel_litros >= SP_LLENO or fallo_sensor:
            self.bomba_auto_marcha = False

        manual = mw["modo_manual"] != 0
        if manual and self.prev_modo == 0:           # paso a manual sin salto
            mw["mando_marcha"] = 1 if self.bomba_auto_marcha else 0
            mw["velocidad_manual"] = VELOCIDAD_AUTO
        self.prev_modo = mw["modo_manual"]

        orden_marcha = (mw["mando_marcha"] != 0) if manual else self.bomba_auto_marcha
        if not seguridades_ok:
            orden_marcha = False

        if self.ton_arranque(orden_marcha and not contactor_cerrado, dt) or \
                self.ton_paro(not orden_marcha and contactor_cerrado, dt):
            self.fallo_arranque = True
        if mw["reset_fallos"] != 0 and not seta_activa:
            self.fallo_arranque = False
        mw["reset_fallos"] = 0                       # reset por pulso

        self.bomba_marcha = 1 if orden_marcha else 0
        if not orden_marcha:
            self.bomba_velo = 0
        elif manual:
            v = mw["velocidad_manual"]
            self.bomba_velo = VELOCIDAD_AUTO if v <= 0 else min(v, 100)
        else:
            self.bomba_velo = VELOCIDAD_AUTO

        if manual:
            self.valvula_abrir = 1 if mw["mando_valvula"] != 0 and not seta_activa else 0
        else:
            self.valvula_abrir = 1 if consumo_permitido else 0

        mw["hmi_nivel_x10"] = 0 if nivel_litros < 0 else round(nivel_litros * 10)
        mw["hmi_nivel_ma"] = io["nivel_ma_x100"]
        mw["hmi_caudal_ent"] = 0 if caudal_ent < 0 else round(caudal_ent * 10)
        mw["hmi_caudal_sal"] = 0 if caudal_sal < 0 else round(caudal_sal * 10)
        mw["hmi_velocidad"] = io["velocidad_real_bomba_pct"]
        bits = [contactor_cerrado, seta_activa, fallo_sensor, self.fallo_arranque, alarma_alto, alarma_bajo,
                self.en_reserva, manual, self.bomba_marcha != 0, self.valvula_abrir != 0]
        mw["hmi_estado"] = sum(1 << i for i, b in enumerate(bits) if b)


@dataclass
class Plant:
    """Deposito de 1000 L: llenado por bomba, vaciado por gravedad a traves de la valvula."""
    nivel: float = 500.0
    velocidad: float = 0.0
    contactor: bool = False
    t_orden: float = 0.0

    def step(self, plc: Plc, faults: dict, dt: float) -> dict:
        speed = max(faults["speed"], 1)
        # contactor: confirma 0,5 s despues de la orden salvo fallo inyectado
        self.t_orden = self.t_orden + dt if plc.bomba_marcha else 0.0
        self.contactor = bool(plc.bomba_marcha) and self.t_orden >= 0.5 and not faults["no_confirm"]
        objetivo = plc.bomba_velo if self.contactor else 0
        paso = 25.0 * dt
        self.velocidad += max(-paso, min(paso, objetivo - self.velocidad))
        q_ent = LPM_POR_PCT * self.velocidad if self.contactor else 0.0
        q_sal = K_DESCARGA * math.sqrt(max(self.nivel, 0.0)) if plc.valvula_abrir else 0.0
        self.nivel = min(1000.0, max(0.0, self.nivel + (q_ent - q_sal) / 60.0 * dt * speed))
        ma = 300 if faults["sensor_fail"] else round(400 + self.nivel / 1000.0 * 1600)
        return {
            "nivel_ma_x100": ma,
            "caudal_entrada": round(400 + q_ent / 150.0 * 1600),
            "caudal_salida": round(400 + q_sal / 150.0 * 1600),
            "confirmacion_marcha": 1 if self.contactor else 0,
            "seta_pulsada": 1 if faults["seta_fisica"] else 0,
            "velocidad_real_bomba_pct": round(self.velocidad),
        }


MW_NAMES = {"hmi_nivel_x10": HR_NIVEL, "hmi_nivel_ma": HR_MA, "hmi_caudal_ent": HR_ENT, "hmi_caudal_sal": HR_SAL,
            "hmi_velocidad": HR_VEL, "hmi_estado": HR_ESTADO, "modo_manual": HR_MODO, "mando_marcha": HR_MARCHA,
            "mando_valvula": HR_VALVULA, "reset_fallos": HR_RESET, "velocidad_manual": HR_CONSIGNA,
            "seta_scada": HR_SETA_SCADA}


class Registers:
    """Memoria del PLC simulado. El servidor Modbus lee y escribe aqui a traves del gancho action."""

    def __init__(self) -> None:
        self.hr = [0] * 2100        # holding registers (%QW y %MW)
        self.ir = [0] * 16          # input registers (%IW)

    def get(self, addr: int) -> int:
        v = self.hr[addr]
        return v - 65536 if v > 32767 else v

    def set(self, addr: int, value: int) -> None:
        self.hr[addr] = value & 0xFFFF

    async def action(self, function_code: int, start_address: int, address: int, count: int,
                     current_registers: list, set_values: list | None):
        table = self.ir if function_code == 4 else self.hr
        if set_values is not None:                  # escritura (FC 6/16)
            for i, v in enumerate(set_values):
                table[address + i] = int(v) & 0xFFFF
        # la respuesta sale siempre de la memoria del PLC (pymodbus anade un registro centinela al bloque)
        for i in range(min(len(current_registers), len(table) - start_address)):
            current_registers[i] = table[start_address + i]
        return None


async def run_logic(regs: Registers, level: float) -> None:
    plc, plant = Plc(), Plant(nivel=level)
    io = plant.step(plc, {"no_confirm": 0, "sensor_fail": 0, "seta_fisica": 0, "speed": 1}, 0.0)
    while True:
        faults = {"no_confirm": regs.get(SIM_NO_CONFIRM), "sensor_fail": regs.get(SIM_SENSOR_FAIL),
                  "seta_fisica": regs.get(SIM_SETA_FISICA), "speed": regs.get(SIM_SPEED)}
        mw = {name: regs.get(addr) for name, addr in MW_NAMES.items()}
        plc.scan(io, mw, SCAN_S)
        for name, addr in MW_NAMES.items():
            regs.set(addr, mw[name])
        regs.hr[0:3] = [plc.bomba_marcha, plc.bomba_velo, plc.valvula_abrir]                    # %QW0..2
        io = plant.step(plc, faults, SCAN_S)
        regs.ir[0:6] = [io["nivel_ma_x100"], io["caudal_entrada"], io["caudal_salida"],          # %IW0..5
                        io["confirmacion_marcha"], io["seta_pulsada"], io["velocidad_real_bomba_pct"]]
        await asyncio.sleep(SCAN_S)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5502)
    parser.add_argument("--level", type=float, default=500.0, help="nivel inicial en L")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    regs = Registers()
    bits = SimData(0, count=16, datatype=DataType.BITS)
    device = SimDevice(id=1, action=regs.action, simdata=(
        [bits], [bits], [SimData(0, count=len(regs.hr), datatype=DataType.REGISTERS)],
        [SimData(0, count=len(regs.ir), datatype=DataType.REGISTERS)]))
    asyncio.create_task(run_logic(regs, args.level))
    log.info("Simulador PLC escuchando en %s:%d (unit 1), nivel inicial %.0f L", args.host, args.port, args.level)
    await StartAsyncTcpServer(context=device, address=(args.host, args.port))


if __name__ == "__main__":
    asyncio.run(main())
