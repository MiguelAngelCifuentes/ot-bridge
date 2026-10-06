from domain.engine import AlarmEngine, Sample
from domain.rules import COMM_RULE, DEFAULT_RULES, Rule

HIGH = Rule("nivel_x10", "gt", 9000, "high", "Nivel alto", code="th1", deadband=100)
DELAYED = Rule("estado", "bit", 16, "high", "Nivel muy alto", code="estado:bit16", delay_s=2)


def s(variable, value, ts, plc="plc01"):
    return Sample(plc, variable, value, ts)


def states(events):
    return [(plc, rule.key, state) for plc, rule, state, _ in events]


# ---------------------------------------------------------------- reglas
def test_compare_operators():
    assert Rule("v", "lt", 10, "low", "").compare(9)
    assert not Rule("v", "lt", 10, "low", "").compare(10)
    assert Rule("v", "le", 10, "low", "").compare(10)
    assert Rule("v", "ge", 10, "low", "").compare(10)
    assert Rule("v", "eq", 0, "low", "").compare(0)
    assert Rule("v", "bit", 4, "low", "").compare(4 | 1)
    assert not Rule("v", "bit", 4, "low", "").compare(3)
    assert not Rule("v", "gt", 1, "low", "").compare("no-numero")
    assert not Rule("v", "xx", 1, "low", "").compare(5)


def test_key_uses_code_or_fallback():
    assert HIGH.key == "th1"
    assert Rule("nivel_x10", "gt", 9000.0, "high", "").key == "nivel_x10:gt:9000"


def test_default_rules_have_unique_codes():
    codes = [r.key for r in DEFAULT_RULES] + [COMM_RULE.key]
    assert len(codes) == len(set(codes))


def test_bit_alarms_are_independent():
    """D13: dos bits CRITICAL del mismo registro son dos alarmas distintas."""
    engine = AlarmEngine()
    rules = DEFAULT_RULES
    events = engine.evaluate(s("estado", 2 | 4, 100), rules)
    assert sorted(k for _, k, st in states(events)) == ["estado:bit2", "estado:bit4"]
    events = engine.evaluate(s("estado", 4, 101), rules)
    assert states(events) == [("plc01", "estado:bit2", "RESOLVED")]


# ---------------------------------------------------------------- histeresis y retardo
def test_hysteresis_prevents_chattering():
    engine = AlarmEngine()
    assert states(engine.evaluate(s("nivel_x10", 9001, 1), (HIGH,))) == [("plc01", "th1", "ACTIVE")]
    # por debajo del umbral pero dentro de la banda muerta: sigue activa
    assert engine.evaluate(s("nivel_x10", 8950, 2), (HIGH,)) == []
    assert engine.evaluate(s("nivel_x10", 9001, 3), (HIGH,)) == []
    assert states(engine.evaluate(s("nivel_x10", 8900, 4), (HIGH,))) == [("plc01", "th1", "RESOLVED")]


def test_activation_delay_uses_sample_timestamps():
    engine = AlarmEngine()
    assert engine.evaluate(s("estado", 16, 10), (DELAYED,)) == []
    assert engine.evaluate(s("estado", 16, 11), (DELAYED,)) == []
    assert states(engine.evaluate(s("estado", 16, 12), (DELAYED,))) == [("plc01", "estado:bit16", "ACTIVE")]


def test_transient_shorter_than_delay_is_ignored():
    engine = AlarmEngine()
    engine.evaluate(s("estado", 16, 10), (DELAYED,))
    engine.evaluate(s("estado", 0, 11), (DELAYED,))          # desaparece: se reinicia el retardo
    assert engine.evaluate(s("estado", 16, 12), (DELAYED,)) == []
    assert engine.evaluate(s("estado", 16, 13), (DELAYED,)) == []
    assert states(engine.evaluate(s("estado", 16, 14), (DELAYED,))) == [("plc01", "estado:bit16", "ACTIVE")]


def test_resolution_delay():
    engine = AlarmEngine()
    engine.evaluate(s("estado", 16, 0), (DELAYED,))
    engine.evaluate(s("estado", 16, 2), (DELAYED,))
    assert engine.evaluate(s("estado", 0, 3), (DELAYED,)) == []
    assert states(engine.evaluate(s("estado", 0, 5), (DELAYED,))) == [("plc01", "estado:bit16", "RESOLVED")]


def test_plcs_are_independent():
    engine = AlarmEngine()
    engine.evaluate(s("nivel_x10", 9500, 1, plc="plc01"), (HIGH,))
    assert engine.evaluate(s("nivel_x10", 100, 2, plc="plc02"), (HIGH,)) == []
    assert ("plc01", "th1") in engine.active_items()


# ---------------------------------------------------------------- reglas retiradas
def test_reconcile_resolves_removed_rule():
    """D5: si la regla desaparece con su alarma activa, la alarma se resuelve."""
    engine = AlarmEngine()
    engine.evaluate(s("nivel_x10", 9500, 1), (HIGH,))
    events = engine.reconcile(())
    assert states(events) == [("plc01", "th1", "RESOLVED")]
    assert engine.active_items() == {}


def test_reconcile_keeps_comm_alarm():
    engine = AlarmEngine()
    engine.comm_lost("plc01")
    assert engine.reconcile(()) == []
    assert ("plc01", "comunicacion") in engine.active_items()


# ---------------------------------------------------------------- comunicacion
def test_comm_loss_raises_alarm_and_freezes_others():
    """D7: perder el PLC no resuelve en silencio: alarma propia y el resto congeladas."""
    engine = AlarmEngine()
    engine.evaluate(s("nivel_x10", 9500, 1), (HIGH,))
    assert states(engine.comm_lost("plc01")) == [("plc01", "comunicacion", "ACTIVE")]
    assert engine.comm_lost("plc01") == []                                   # idempotente
    assert engine.evaluate(s("nivel_x10", 0, 2), (HIGH,)) == []             # congelada
    assert ("plc01", "th1") in engine.active_items()
    assert states(engine.comm_restored("plc01")) == [("plc01", "comunicacion", "RESOLVED")]
    assert engine.comm_restored("plc01") == []
    assert states(engine.evaluate(s("nivel_x10", 0, 3), (HIGH,))) == [("plc01", "th1", "RESOLVED")]


def test_comm_loss_discards_pending_delays():
    engine = AlarmEngine()
    engine.evaluate(s("estado", 16, 10), (DELAYED,))
    engine.comm_lost("plc01")
    engine.comm_restored("plc01")
    assert engine.evaluate(s("estado", 16, 20), (DELAYED,)) == []           # el retardo empieza de nuevo


# ---------------------------------------------------------------- persistencia
def test_dump_and_load_roundtrip():
    engine = AlarmEngine()
    engine.evaluate(s("nivel_x10", 9500, 1), (HIGH,))
    engine.comm_lost("plc01")
    restored = AlarmEngine()
    restored.load_states(engine.dump_states())
    assert restored.active_items() == engine.active_items()
    assert restored.is_comm_lost("plc01")


def test_load_legacy_format_and_garbage():
    engine = AlarmEngine()
    engine.load_states({"plc01|th1": {"variable": "nivel_x10", "op": "gt", "value": 9000, "severity": "high",
                                      "message": "x"},
                        "roto": {"variable": "x"}})
    assert list(engine.active_items()) == [("plc01", "th1")]
    assert not engine.is_comm_lost("plc01")
