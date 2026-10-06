"""Gemelo de balance de masas: caudales del contrato en l/min x10, nivel en L x10."""
from domain.twin import RESYNC_GAP_S, MassBalanceTwin

GAIN = 0.005
THRESHOLD = 20.0


def run(twin, level_l, ent_lpm, sal_lpm, seconds, t0=0):
    """Simula `seconds` s a 1 Hz; el nivel real evoluciona con los caudales dados (l/min reales)."""
    update = None
    for i in range(seconds):
        ts = t0 + i
        twin.update("caudal_ent", ent_lpm * 10, ts)
        twin.update("caudal_sal", sal_lpm * 10, ts)
        update = twin.update("nivel_x10", round(level_l * 10), ts)
        level_l += (ent_lpm - sal_lpm) / 60.0
        yield update, level_l


def last(gen):
    out = None
    for out in gen:
        pass
    return out


def test_non_level_variables_return_nothing():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    assert twin.update("caudal_ent", 900, 0) is None
    assert twin.update("velocidad", 50, 0) is None


def test_first_level_initializes_model():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    update = twin.update("nivel_x10", 5000, 0)
    assert update.state.level_model == 500.0 and update.event is None


def test_balanced_plant_tracks_without_alarm():
    """Con FLOW_DIVISOR=10 el modelo sigue a la planta (con el divisor mal, derivaria 10x)."""
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    update, _ = last(run(twin, 400.0, ent_lpm=90, sal_lpm=60, seconds=600))
    assert abs(update.state.deviation) < 1.0
    assert abs(update.state.leak_lpm) < 0.5
    assert not update.state.alarmed


def test_wrong_divisor_would_drift():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 1)
    update, _ = last(run(twin, 400.0, ent_lpm=90, sal_lpm=60, seconds=120))
    assert abs(update.state.deviation) > THRESHOLD


def test_unmeasured_leak_raises_and_estimates_flow():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    level = 500.0
    events = []
    # fuga de 12 l/min no medida: el nivel real baja 12 l/min mas de lo que dicen los caudales
    for i in range(1800):
        twin.update("caudal_ent", 600, i)
        twin.update("caudal_sal", 600, i)
        update = twin.update("nivel_x10", round(level * 10), i)
        level -= 12 / 60.0
        if update.event:
            events.append(update.event)
    assert events == ["ACTIVE"]
    assert 9.0 < update.state.leak_lpm < 13.0          # estimacion en l/min reales


def test_leak_stops_then_alarm_resolves():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    level = 500.0
    for i in range(1800):
        twin.update("caudal_ent", 0, i)
        twin.update("caudal_sal", 0, i)
        twin.update("nivel_x10", round(level * 10), i)
        level -= 12 / 60.0
    events = []
    for i in range(1800, 3600):
        update = twin.update("nivel_x10", round(level * 10), i)
        if update.event:
            events.append(update.event)
    assert events == ["RESOLVED"]


def test_resync_after_gap():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    twin.update("nivel_x10", 5000, 0)
    update = twin.update("nivel_x10", 2000, int(RESYNC_GAP_S) + 10)
    assert update.state.level_model == 200.0 and update.event is None


def test_short_gap_integrates_normally():
    twin = MassBalanceTwin(THRESHOLD, GAIN, 10)
    twin.update("caudal_ent", 600, 0)
    twin.update("nivel_x10", 5000, 0)
    update = twin.update("nivel_x10", 5050, 5)          # 5 s a 60 l/min = +5 L: integra, no resincroniza
    assert abs(update.state.deviation) < 0.5
