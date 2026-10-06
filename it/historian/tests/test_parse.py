import json

from app.handler import parse_message
from domain.models import PlcStatus, Reading, TwinState


def payload(**kw):
    return json.dumps(kw).encode()


def test_valid_reading():
    msg = parse_message("factory/plc01/telemetry/caudal_ent",
                        payload(ts=100, plc="plc01", variable="caudal_ent", value=905, unit="lpm_x10", q=1))
    assert msg == Reading("plc01", "caudal_ent", 905, "lpm_x10", 100, 1)


def test_bad_quality_is_discarded():
    assert parse_message("factory/plc01/telemetry/nivel_x10",
                         payload(ts=100, plc="plc01", variable="nivel_x10", value=0, unit="L_x10", q=0)) is None


def test_negative_value_kept_as_int():
    msg = parse_message("factory/plc01/telemetry/x", payload(ts=1, plc="plc01", variable="x", value=-5))
    assert msg.value == -5 and msg.q == 1


def test_malformed_payloads_are_discarded():
    assert parse_message("factory/plc01/telemetry/x", b"no-json") is None
    assert parse_message("factory/plc01/telemetry/x", payload(plc="plc01", value=1)) is None
    assert parse_message("factory/plc01/status", payload(plc="plc01")) is None


def test_status_including_lwt_with_zero_ts():
    msg = parse_message("factory/plc01/status", payload(ts=0, plc="plc01", online=False))
    assert msg == PlcStatus("plc01", False, 0)          # el writer decide descartar ts<=0


def test_twin_state():
    msg = parse_message("factory/plc01/twin/state",
                        payload(plc="plc01", ts=5, level_real=500.1, level_model=499.9, deviation=0.2,
                                leak_lpm=0.06, threshold=20, alarmed=False))
    assert isinstance(msg, TwinState) and msg.leak_lpm == 0.06


def test_unknown_topic():
    assert parse_message("factory/alarms/events", payload(a=1)) is None


# ---------------------------------------------------------------- writer (sin conexion real)
def writer():
    from types import SimpleNamespace

    from adapters.influx_writer import InfluxWriter
    cfg = SimpleNamespace(influx_host="localhost", influx_port=8086, influx_user="u", influx_password="p",
                          influx_db="plant")
    return InfluxWriter(cfg)


def test_writer_discards_invalid_ts_and_buffers_valid():
    w = writer()
    w.add_reading(Reading("plc01", "nivel_x10", 5000, "L_x10", 0))
    w.add_status(PlcStatus("plc01", False, 0))                     # LWT con ts=0
    assert len(w._buffer) == 0
    w.add_reading(Reading("plc01", "nivel_x10", 5000, "L_x10", 100))
    (point,) = w._buffer
    assert point["time"] == 100 * 1_000_000_000 and point["fields"] == {"value": 5000}
