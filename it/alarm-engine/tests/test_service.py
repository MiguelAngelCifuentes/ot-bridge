"""Reconciliacion motor <-> API (autorreparacion tras perder eventos) con dobles de prueba."""
from app.service import AlarmService
from domain.engine import Sample
from domain.rules import Rule

HIGH = Rule("nivel_x10", "gt", 9000, "high", "Nivel alto", code="th1")


class FakeMqtt:
    def __init__(self):
        self.events = []

    def publish_event(self, plc, variable, severity, state, message, code):
        self.events.append((plc, code, state))


class FakeApi:
    def __init__(self, open_alarms):
        self.open_alarms = open_alarms

    def fetch_open_alarms(self):
        return self.open_alarms


class FakeStore:
    def save(self, data):
        self.saved = data


def service(open_alarms):
    mqtt = FakeMqtt()
    svc = AlarmService(mqtt, FakeApi(open_alarms), 30, FakeStore())
    return svc, mqtt


def api_alarm(code, variable="nivel_x10"):
    return {"machineName": "plc01", "code": code, "variable": variable, "severity": "high", "message": "m"}


def test_republishes_active_alarm_missing_in_api():
    svc, mqtt = service([])
    svc._engine.comm_lost("plc01")
    svc._reconcile_with_api()
    assert mqtt.events == [("plc01", "comunicacion", "ACTIVE")]


def test_closes_stale_alarm_owned_by_engine():
    svc, mqtt = service([api_alarm("th1"), api_alarm("comunicacion", "comunicacion")])
    svc._reconcile_with_api()
    assert sorted(mqtt.events) == [("plc01", "comunicacion", "RESOLVED"), ("plc01", "th1", "RESOLVED")]


def test_ignores_alarms_owned_by_others():
    """Las alarmas del gemelo digital (gemelo:balance) no las cierra el motor."""
    svc, mqtt = service([api_alarm("gemelo:balance", "desviacion")])
    svc._reconcile_with_api()
    assert mqtt.events == []


def test_no_events_when_in_sync():
    svc, mqtt = service([api_alarm("th1")])
    svc._engine.evaluate(Sample("plc01", "nivel_x10", 9500, 1), (HIGH,))
    svc._reconcile_with_api()
    assert mqtt.events == []


def test_api_unreachable_does_nothing():
    svc, mqtt = service(None)
    svc._engine.comm_lost("plc01")
    svc._reconcile_with_api()
    assert mqtt.events == []
