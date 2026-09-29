"""Tests de visitas, comida servida y avisos (lógica pura):  python tests/test_service_monitor.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.service_monitor import FoodMonitor, VisitDetector
from backend.services.table_state import EVENT_ALERT, EVENT_SERVED, EVENT_VISIT, TableEngine


def feed_visits(v, seconds, ids_by_t):
    out = []
    for i in range(int(seconds * 10)):
        t = i / 10
        out += v.update(t, ids_by_t(t))
    return out


def test_walk_in_and_leave_is_a_visit():
    v = VisitDetector(min_seconds=1.5, max_seconds=60, leave_grace=1)
    visits = feed_visits(v, 20, lambda t: [(7, True)] if 5 <= t < 10 else [])
    assert len(visits) == 1 and visits[0]["t"] == 5 and abs(visits[0]["duration"] - 4.9) < 0.11


def test_seated_customer_with_new_id_is_not_a_visit():
    v = VisitDetector(1.5, 60, 1)
    # el ID reaparece ya DENTRO de la mesa (walked_in=False) y luego se va
    assert feed_visits(v, 20, lambda t: [(9, False)] if 2 <= t < 8 else []) == []


def test_quick_pass_and_long_stay_are_not_visits():
    v = VisitDetector(1.5, 10, 1)
    visits = feed_visits(v, 60, lambda t: ([(1, True)] if 5 <= t < 5.5 else []) + ([(2, True)] if 10 <= t < 40 else []))
    assert visits == []


def test_food_needs_sustained_increase_over_baseline():
    f = FoodMonitor(confirm_seconds=3)
    for i in range(20):                       # 2 copas ya en la mesa al sentarse
        f.add_sample(i * 0.5, 2)
    f.begin_occupancy()
    f.add_sample(10.5, 4)                     # un solo pico no cuenta
    assert f.served_at(10.5) is None
    for i in range(30):
        f.add_sample(11 + i * 0.5, 4)         # plato + bebida sostenidos
    assert f.served_at(25.0) is not None


def test_alerts_fire_once_per_occupancy():
    e = TableEngine(2, 3, get_settings=lambda: {"unattended_seconds": 10, "long_stay_seconds": 20})
    e.sync_tables(["T01"])
    for i in range(400):
        e.update(i / 10, {"T01": 2 if i < 300 else 0})
    kinds = [x["alert"] for x in e.log.events if x["type"] == EVENT_ALERT]
    assert kinds.count("UNATTENDED") == 1 and kinds.count("LONG_STAY") == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
