"""Lectura Modbus TCP de diagnostico contra el PLC (solo FC03). Uso: python scripts/test_read_plc.py <host_PLC>"""

import os
import sys

from pymodbus.client import ModbusTcpClient

# (direccion Modbus 0-based, registro, variable del contrato, divisor a unidades de ingenieria, unidad)
REGISTERS = [
    (1124, "MW100", "nivel_x10", 10, "L"),
    (1125, "MW101", "nivel_ma", 100, "mA"),
    (1126, "MW102", "caudal_ent", 10, "l/min"),
    (1127, "MW103", "caudal_sal", 10, "l/min"),
    (1128, "MW104", "velocidad", 1, "%"),
    (1129, "MW105", "estado", 1, "bitmask"),
]

# Bits de hmi_estado con los nombres del programa PLC (ot/plc/pous/programs/main.st)
STATUS_BITS = {
    1: "contactor_cerrado",
    2: "seta_activa",
    4: "fallo_sensor",
    8: "fallo_arranque",
    16: "alarma_nivel_alto",
    32: "alarma_nivel_bajo",
    64: "en_reserva",
    128: "modo_manual",
    256: "orden_marcha_bomba",
    512: "orden_apertura_valvula",
}


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PLC_HOST")
    if not host:
        print("Uso: python scripts/test_read_plc.py <IP_PC1>  (o definir PLC_HOST)")
        return 2

    client = ModbusTcpClient(host, port=502, timeout=3)
    if not client.connect():
        print(f"ERROR: no se pudo conectar a {host}:502")
        return 1

    try:
        base = REGISTERS[0][0]
        result = client.read_holding_registers(address=base, count=len(REGISTERS), device_id=1)
        if result.isError():
            print(f"ERROR Modbus: {result}")
            return 1

        print(f"Lectura de {host}:502 (FC03, dir {base}, count={len(REGISTERS)}, unit_id=1)")
        for (address, mw, name, divisor, unit), value in zip(REGISTERS, result.registers):
            scaled = f"{value / divisor:.2f} {unit}" if divisor != 1 else f"{value} {unit}"
            print(f"  {mw} (dir {address})  {name:<12} = {value:>6}  -> {scaled}")

        estado = result.registers[5]
        activos = [label for bit, label in STATUS_BITS.items() if estado & bit]
        print(f"\n  estado -> bits activos: {', '.join(activos) if activos else 'ninguno'}")

        if any(result.registers):
            print(f"  OK: 6 registros con datos (nivel = {result.registers[0] / 10:.1f} L)")
            return 0

        print("  AVISO: todos los registros a 0 (¿PLC parado o dirección incorrecta?)")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
