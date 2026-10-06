from pathlib import Path

import pytest

from adapters.modbus_poller import to_int16
from config import load_config

CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"

# Contrato MQTT (docs/mqtt-contract.md): variable -> (direccion Modbus, unidad)
CONTRACT = {
    "nivel_x10": (1124, "L_x10"), "nivel_ma": (1125, "mA_x100"), "caudal_ent": (1126, "lpm_x10"),
    "caudal_sal": (1127, "lpm_x10"), "velocidad": (1128, "%"), "estado": (1129, "bitmask"),
    "modo_manual": (1130, ""), "mando_marcha": (1131, ""), "mando_valvula": (1132, ""),
    "reset_fallos": (1133, ""), "consigna_manual": (1134, "%"), "seta_scada": (1135, ""),
}


@pytest.mark.parametrize("raw,expected", [(0, 0), (1500, 1500), (0x7FFF, 32767), (0x8000, -32768),
                                          (0xFFFF, -1), (65535 - 99, -100)])
def test_to_int16(raw, expected):
    assert to_int16(raw) == expected


def test_config_matches_contract(monkeypatch):
    monkeypatch.delenv("PLC_HOST", raising=False)
    config = load_config(CONFIG)
    (plc,) = config.plcs
    assert plc.name == "plc01" and plc.host == "openplc-runtime"
    assert {r.name: (r.address, r.unit) for r in plc.registers} == CONTRACT


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PLC_HOST", "192.0.2.10")
    monkeypatch.setenv("MQTT_BROKER", "mosquitto")
    monkeypatch.setenv("MQTT_USER", "gateway")
    config = load_config(CONFIG)
    assert config.plcs[0].host == "192.0.2.10"
    assert config.broker.host == "mosquitto" and config.broker.username == "gateway"


def test_non_contiguous_registers_rejected(tmp_path):
    bad = tmp_path / "c.yaml"
    bad.write_text("plcs:\n  - name: p\n    host: h\n    registers:\n"
                   "      - {address: 1, name: a}\n      - {address: 3, name: b}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contiguos"):
        load_config(bad)
