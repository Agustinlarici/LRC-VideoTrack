"""Tests de la lógica de mesas (sin YOLO ni OpenCV):  python -m pytest tests  (o python tests/test_table_state.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.table_state import (EVENT_FREED, EVENT_OCCUPIED, FREE, OCCUPIED, TableEngine)


def run(engine, samples):
    for t, counts in samples:
        engine.update(t, counts)


def make():
    e = TableEngine(occupy_seconds=5, free_seconds=10)
    e.sync_tables(["T01"])
    return e


def test_person_passing_by_does_not_occupy():
    e = make()
    run(e, [(t, {"T01": 1 if 2 <= t <= 4 else 0}) for t in range(0, 30)])
    assert e.tables["T01"].status == FREE and e.log.events == []


def test_occupy_then_free_with_duration():
    e = make()
    run(e, [(t, {"T01": 2}) for t in range(10, 40)])          # llegan en t=10
    assert e.tables["T01"].status == OCCUPIED
    run(e, [(t, {"T01": 0}) for t in range(40, 60)])          # se van en t=40
    assert e.tables["T01"].status == FREE
    occ, freed = e.log.events
    assert (occ["type"], occ["t"], occ["people_count"]) == (EVENT_OCCUPIED, 10, 2)
    assert (freed["type"], freed["t"], freed["people_count"]) == (EVENT_FREED, 40, 2)
    assert freed["duration"] == 30


def test_short_gap_while_occupied_does_not_free():
    e = make()
    run(e, [(t, {"T01": 1}) for t in range(0, 10)])
    run(e, [(t, {"T01": 0}) for t in range(10, 15)])          # 5 s ausente (< 10 s)
    run(e, [(t, {"T01": 1}) for t in range(15, 20)])
    assert e.tables["T01"].status == OCCUPIED and len(e.log.events) == 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
