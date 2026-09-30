"""Registro persistente en SQLite (un archivo local, sin servidor).

Fuente de la verdad = tabla `events` (cada cosa que pasa en una mesa) + `samples` (foto cada pocos
segundos: estado, personas y objetos por mesa). Las sesiones y estadísticas se CALCULAN a partir de
ahí (journal.py), así el historial y el dashboard en vivo usan exactamente los mismos datos.
"""
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, clock_start TEXT, created_at TEXT, settings TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL, table_id TEXT NOT NULL, type TEXT NOT NULL,
    t REAL, ts TEXT NOT NULL, people_count INTEGER, payload TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id);
CREATE TABLE IF NOT EXISTS samples (
    run_id INTEGER NOT NULL, table_id TEXT NOT NULL, t REAL, ts TEXT NOT NULL,
    status TEXT, people INTEGER, items INTEGER
);
CREATE INDEX IF NOT EXISTS ix_samples ON samples(run_id, table_id, ts);
"""


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class Storage:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or config.DB_FILE)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    # ---------- escritura ----------
    def new_run(self, source: str, clock_start: datetime, settings: dict) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO runs(source, clock_start, created_at, settings) VALUES (?,?,?,?)",
                (source, clock_start.isoformat(), datetime.now().isoformat(), json.dumps(settings)))
            self._db.commit()
            return cur.lastrowid

    def add_event(self, run_id: int, table_id: str, type_: str, t: float, ts: datetime, people_count: int, payload: dict):
        with self._lock:
            self._db.execute(
                "INSERT INTO events(run_id, table_id, type, t, ts, people_count, payload) VALUES (?,?,?,?,?,?,?)",
                (run_id, table_id, type_, t, ts.isoformat(), people_count, json.dumps(payload, default=str)))
            self._db.commit()

    def add_samples(self, run_id: int, rows: list[tuple]):
        """rows: (table_id, t, ts(datetime), status, people, items)"""
        with self._lock:
            self._db.executemany(
                "INSERT INTO samples(run_id, table_id, t, ts, status, people, items) VALUES (?,?,?,?,?,?,?)",
                [(run_id, r[0], r[1], r[2].isoformat(), r[3], r[4], r[5]) for r in rows])
            self._db.commit()

    def delete_run(self, run_id: int):
        with self._lock:
            for table in ("events", "samples"):
                self._db.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
            self._db.execute("DELETE FROM runs WHERE id=?", (run_id,))
            self._db.commit()

    def delete_all(self):
        with self._lock:
            for table in ("events", "samples", "runs"):
                self._db.execute(f"DELETE FROM {table}")
            self._db.commit()

    # ---------- lectura ----------
    def days(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT substr(ts,1,10) AS day, COUNT(*) AS events, COUNT(DISTINCT run_id) AS runs "
                "FROM events GROUP BY day ORDER BY day DESC").fetchall()
        return [dict(r) for r in rows]

    def runs(self, date: str | None = None) -> list[dict]:
        where, args = ("WHERE substr(e.ts,1,10)=?", (date,)) if date else ("", ())
        with self._lock:
            rows = self._db.execute(
                f"SELECT r.id, r.source, r.clock_start, r.created_at, MIN(e.ts) AS first_ts, MAX(e.ts) AS last_ts, "
                f"COUNT(e.id) AS events FROM runs r JOIN events e ON e.run_id = r.id {where} "
                f"GROUP BY r.id ORDER BY r.id DESC", args).fetchall()
        return [dict(r) for r in rows]

    def events(self, date: str | None = None, run_id: int | None = None) -> list[dict]:
        clauses, args = [], []
        if date:
            clauses.append("substr(ts,1,10)=?"); args.append(date)
        if run_id is not None:
            clauses.append("run_id=?"); args.append(run_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM events {where} ORDER BY run_id, ts, id", args).fetchall()
        return [{**dict(r), "ts": _parse(r["ts"]), "payload": json.loads(r["payload"] or "{}")} for r in rows]

    def samples(self, run_id: int, table_id: str, start: datetime, end: datetime) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, status, people, items FROM samples WHERE run_id=? AND table_id=? AND ts>=? AND ts<=? ORDER BY ts",
                (run_id, table_id, start.isoformat(), end.isoformat())).fetchall()
        return [dict(r) for r in rows]

    def observed_seconds(self, date: str | None = None, run_id: int | None = None) -> float:
        """Tiempo total observado (suma, por ejecución, de último - primer registro)."""
        clauses, args = [], []
        if date:
            clauses.append("substr(ts,1,10)=?"); args.append(date)
        if run_id is not None:
            clauses.append("run_id=?"); args.append(run_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock:
            rows = self._db.execute(
                f"SELECT MIN(ts) AS a, MAX(ts) AS b FROM (SELECT run_id, ts FROM samples UNION ALL "
                f"SELECT run_id, ts FROM events) {where} GROUP BY run_id", args).fetchall()
        return sum((_parse(r["b"]) - _parse(r["a"])).total_seconds() for r in rows)

    def run_ends(self) -> dict[int, datetime]:
        """Último instante registrado (evento o foto) de cada ejecución."""
        with self._lock:
            rows = self._db.execute(
                "SELECT run_id, MAX(ts) AS b FROM (SELECT run_id, ts FROM samples UNION ALL "
                "SELECT run_id, ts FROM events) GROUP BY run_id").fetchall()
        return {r["run_id"]: _parse(r["b"]) for r in rows}
