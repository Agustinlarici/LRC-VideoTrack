"""Diario de mesas: reconstruye cada VISITA (grupo sentado) a partir de los eventos y calcula
estadísticas de restaurante. Lógica pura, sin base de datos ni OpenCV."""
from datetime import datetime, timedelta
from statistics import median

OCC, FREED = "TABLE_OCCUPIED", "TABLE_FREED"


def _secs(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds()


def build_sessions(events: list[dict], now: datetime | None = None, run_ends: dict | None = None,
                   active_run: int | None = None) -> list[dict]:
    """`events`: dicts con run_id, table_id, type, ts(datetime), people_count, payload(dict), ordenados por
    (run_id, ts). `run_ends`: último instante registrado de cada ejecución (para las visitas sin salida);
    `active_run`: ejecución que sigue en marcha. Una visita sin salida en una ejecución ya terminada queda
    como "cut" (el vídeo/cámara terminó con la mesa ocupada). Devuelve las visitas por hora de inicio."""
    open_: dict[tuple, dict] = {}
    last_closed: dict[tuple, dict] = {}
    sessions: list[dict] = []
    last_ts: dict[int, datetime] = {}

    for e in events:
        key = (e["run_id"], e["table_id"])
        last_ts[e["run_id"]] = e["ts"]
        s = open_.get(key)
        kind, p = e["type"], e["payload"]

        if kind == OCC:
            n = e["people_count"]
            s = {
                "id": f'{e["run_id"]}:{e["table_id"]}:{e["ts"].isoformat()}',
                "run_id": e["run_id"], "table_id": e["table_id"], "start": e["ts"], "end": None,
                "party_initial": n, "party_peak": n, "party_min": n, "party_final": n, "party_changes": 0,
                "visits": [], "first_visit_after": None, "served_after": None, "cleared_after": None,
                "items_peak": 0, "alerts": [], "cleaned_after": None, "turnaround": None, "status": "open",
            }
            prev = last_closed.get(key)
            if prev is not None:
                s["turnaround"] = _secs(prev["end"], e["ts"])
            open_[key] = s
            sessions.append(s)
        elif kind == FREED and s is not None:
            s["end"], s["status"] = e["ts"], "closed"
            s["duration"] = _secs(s["start"], e["ts"])
            del open_[key]
            last_closed[key] = s
        elif kind == "TABLE_CLEANED":
            prev = last_closed.get(key)
            if prev is not None and prev["cleaned_after"] is None:
                prev["cleaned_after"] = max(0.0, _secs(prev["end"], e["ts"]))
        elif s is not None:
            if kind == "TABLE_STAFF_VISIT":
                s["visits"].append({"ts": e["ts"], "duration": p.get("duration")})
                if s["first_visit_after"] is None:
                    s["first_visit_after"] = max(0.0, _secs(s["start"], e["ts"]))
            elif kind == "TABLE_SERVED":
                s["served_after"] = max(0.0, _secs(s["start"], e["ts"]))
            elif kind == "TABLE_CLEARED":
                s["cleared_after"] = max(0.0, _secs(s["start"], e["ts"]))
            elif kind == "PARTY_SIZE_CHANGED":
                n = e["people_count"]
                s["party_changes"] += 1
                s["party_peak"], s["party_min"], s["party_final"] = max(s["party_peak"], n), min(s["party_min"], n), n
            elif kind == "ITEMS_CHANGED":
                s["items_peak"] = max(s["items_peak"], p.get("items", 0))
            elif kind == "ALERT":
                s["alerts"].append({"type": p.get("alert"), "message": p.get("message"), "ts": e["ts"]})

    for s in sessions:
        if s["end"] is None:  # visita sin salida: hasta el último registro de esa ejecución
            end = now or (run_ends or {}).get(s["run_id"]) or last_ts.get(s["run_id"], s["start"])
            s["duration"] = max(0.0, _secs(s["start"], end))
            if active_run is not None and s["run_id"] != active_run:
                s["status"] = "cut"
            elif active_run is None and run_ends is not None:
                s["status"] = "cut"
        s["party_size"] = s["party_peak"]
    return sorted(sessions, key=lambda s: s["start"])


def _avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summarize(sessions: list[dict], observed_seconds: float | None = None) -> dict:
    """Estadísticas del conjunto de visitas. `observed_seconds` = tiempo total observado (suma de las
    ejecuciones) para calcular el % de ocupación."""
    closed = [s for s in sessions if s["status"] == "closed"]  # las "cut"/"open" no cuentan para la estancia media
    tables = sorted({s["table_id"] for s in sessions})
    served = [s for s in sessions if s["served_after"] is not None]
    visited = [s for s in sessions if s["first_visit_after"] is not None]
    occupied_total = sum(s["duration"] for s in sessions)

    per_table = []
    for tid in tables:
        ts_ = [s for s in sessions if s["table_id"] == tid]
        cl = [s for s in ts_ if s["status"] == "closed"]
        per_table.append({
            "table_id": tid, "sessions": len(ts_), "covers": sum(s["party_peak"] for s in ts_),
            "avg_stay": _avg([s["duration"] for s in cl]),
            "occupied_seconds": sum(s["duration"] for s in ts_),
            "occupancy_pct": round(100 * sum(s["duration"] for s in ts_) / observed_seconds, 1) if observed_seconds else None,
            "avg_turnaround": _avg([s["turnaround"] for s in ts_]),
            "avg_first_visit": _avg([s["first_visit_after"] for s in ts_]),
            "avg_service": _avg([s["served_after"] for s in ts_]),
        })

    alerts: dict[str, int] = {}
    for s in sessions:
        for a in s["alerts"]:
            alerts[a["type"]] = alerts.get(a["type"], 0) + 1

    return {
        "sessions": len(sessions),
        "closed": len(closed),
        "covers": sum(s["party_peak"] for s in sessions),
        "avg_party": _avg([s["party_peak"] for s in sessions]),
        "avg_stay": _avg([s["duration"] for s in closed]),
        "median_stay": median([s["duration"] for s in closed]) if closed else None,
        "avg_turnaround": _avg([s["turnaround"] for s in sessions]),
        "avg_first_visit": _avg([s["first_visit_after"] for s in visited]),
        "unattended_pct": round(100 * (len(sessions) - len(visited)) / len(sessions), 1) if sessions else None,
        "avg_service": _avg([s["served_after"] for s in served]),
        "served_pct": round(100 * len(served) / len(sessions), 1) if sessions else None,
        "party_changes": sum(s["party_changes"] for s in sessions),
        "alerts": alerts,
        "occupancy_pct": round(100 * occupied_total / (observed_seconds * len(tables)), 1)
        if observed_seconds and tables else None,
        "tables": len(tables),
        "per_table": per_table,
        "by_hour": by_hour(sessions),
    }


def by_hour(sessions: list[dict]) -> list[dict]:
    """Por hora del día: visitas que empezaron y mesas ocupadas de media (integrando los intervalos)."""
    if not sessions:
        return []
    hours: dict[str, dict] = {}
    for s in sessions:
        end = s["end"] or (s["start"] + timedelta(seconds=s["duration"]))
        cur = s["start"]
        while cur < end:
            bucket = cur.replace(minute=0, second=0, microsecond=0)
            nxt = bucket + timedelta(hours=1)
            seg_end = min(end, nxt)
            h = hours.setdefault(bucket.isoformat(), {"hour": bucket.isoformat(), "started": 0, "occupied_seconds": 0.0})
            h["occupied_seconds"] += _secs(cur, seg_end)
            cur = seg_end
        b = s["start"].replace(minute=0, second=0, microsecond=0).isoformat()
        hours.setdefault(b, {"hour": b, "started": 0, "occupied_seconds": 0.0})["started"] += 1
    out = []
    for key in sorted(hours):
        h = hours[key]
        out.append({"hour": h["hour"], "started": h["started"], "avg_occupied": round(h["occupied_seconds"] / 3600, 2)})
    return out


def public(session: dict) -> dict:
    """Versión serializable a JSON de una visita."""
    def iso(v):
        return v.isoformat() if isinstance(v, datetime) else v
    d = dict(session)
    d["start"], d["end"] = iso(d["start"]), iso(d["end"])
    d["visits"] = [{"ts": iso(v["ts"]), "duration": v["duration"]} for v in d["visits"]]
    d["alerts"] = [{**a, "ts": iso(a["ts"])} for a in d["alerts"]]
    return d
