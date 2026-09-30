"""Tests del diario de mesas y estadísticas (lógica pura):  python tests/test_journal.py"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import journal

T0 = datetime(2026, 9, 30, 20, 0, 0)


def ev(sec, table, kind, people=0, **payload):
    return {"run_id": 1, "table_id": table, "type": kind, "ts": T0 + timedelta(seconds=sec),
            "people_count": people, "payload": payload}


EVENTS = [
    ev(0, "T01", "TABLE_OCCUPIED", 2),
    ev(120, "T01", "TABLE_STAFF_VISIT", 1, duration=20),
    ev(600, "T01", "TABLE_SERVED", 2),
    ev(900, "T01", "PARTY_SIZE_CHANGED", 4, prev=2),
    ev(3000, "T01", "TABLE_FREED", 4, duration=3000),
    ev(3200, "T01", "TABLE_CLEANED", 0, duration=40),
    ev(3600, "T01", "TABLE_OCCUPIED", 3),
    ev(3700, "T02", "TABLE_OCCUPIED", 2),
    ev(3800, "T02", "ALERT", 2, alert="UNATTENDED", message="T02 sin atender"),
    ev(4000, "T02", "TABLE_FREED", 2, duration=300),
]


def test_sessions_are_rebuilt_from_events():
    sessions = journal.build_sessions(EVENTS, run_ends={1: T0 + timedelta(seconds=4200)})
    assert [(s["table_id"], s["status"]) for s in sessions] == [("T01", "closed"), ("T01", "cut"), ("T02", "closed")]
    a, b, c = sessions
    assert a["duration"] == 3000 and a["party_initial"] == 2 and a["party_peak"] == 4 and a["party_changes"] == 1
    assert a["first_visit_after"] == 120 and a["served_after"] == 600 and a["cleaned_after"] == 200
    assert b["turnaround"] == 600 and b["duration"] == 600          # 3600 -> último registro 4200
    assert c["alerts"][0]["type"] == "UNATTENDED"


def test_summary_metrics():
    sessions = journal.build_sessions(EVENTS, run_ends={1: T0 + timedelta(seconds=4200)})
    sm = journal.summarize(sessions, observed_seconds=4200)
    assert sm["sessions"] == 3 and sm["covers"] == 4 + 3 + 2 and sm["closed"] == 2
    assert sm["avg_stay"] == (3000 + 300) / 2 and sm["avg_first_visit"] == 120 and sm["unattended_pct"] == round(200 / 3, 1)
    assert sm["avg_turnaround"] == 600 and sm["alerts"] == {"UNATTENDED": 1}
    assert {t["table_id"] for t in sm["per_table"]} == {"T01", "T02"}
    hours = {h["hour"]: h for h in sm["by_hour"]}
    assert hours["2026-09-30T20:00:00"]["started"] == 1 and hours["2026-09-30T21:00:00"]["started"] == 2
    assert abs(sum(h["avg_occupied"] for h in sm["by_hour"]) * 3600 - (3000 + 600 + 300)) < 20  # avg_occupied va redondeado a 2 decimales


def test_open_session_of_active_run_stays_open():
    sessions = journal.build_sessions(EVENTS[:1], now=T0 + timedelta(seconds=50), active_run=1)
    assert sessions[0]["status"] == "open" and sessions[0]["duration"] == 50


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
