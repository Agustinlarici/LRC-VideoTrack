"""Lógica de negocio: estado de cada mesa con debounce y registro de eventos.

Trabaja en segundos de vídeo (`t`), sin saber nada de YOLO ni de OpenCV.

    LIBERA   --(hay gente >= occupy_seconds seguidos)--> OCCUPATA   (TABLE_OCCUPIED)
    OCCUPATA --(sin gente >= free_seconds seguidos)----> LIBERA     (TABLE_FREED)

El timestamp del evento es el instante en que empezó el cambio (no el de la confirmación),
para que la hora de ocupación sea la real.
"""
from dataclasses import dataclass, field

FREE = "LIBERA"
OCCUPIED = "OCCUPATA"

EVENT_OCCUPIED = "TABLE_OCCUPIED"
EVENT_FREED = "TABLE_FREED"


@dataclass
class TableState:
    table_id: str
    occupy_seconds: float
    free_seconds: float
    status: str = FREE
    people_count: int = 0
    occupied_since: float | None = None
    _candidate_since: float | None = None
    _candidate_peak: int = 0
    _last_people: int = 0  # última cantidad > 0 vista mientras estaba ocupada

    def update(self, t: float, count: int) -> dict | None:
        """Procesa el conteo de un frame. Devuelve un evento si hubo transición."""
        self.people_count = count

        if self.status == FREE:
            if count > 0:
                if self._candidate_since is None:
                    self._candidate_since, self._candidate_peak = t, 0
                self._candidate_peak = max(self._candidate_peak, count)
                if t - self._candidate_since >= self.occupy_seconds:
                    since, peak = self._candidate_since, self._candidate_peak
                    self.status, self.occupied_since = OCCUPIED, since
                    self._candidate_since, self._last_people = None, peak
                    return {"type": EVENT_OCCUPIED, "table_id": self.table_id, "t": since, "people_count": peak}
            else:
                self._candidate_since = None
            return None

        # OCCUPATA
        if count > 0:
            self._candidate_since = None
            self._last_people = count
        else:
            if self._candidate_since is None:
                self._candidate_since = t
            if t - self._candidate_since >= self.free_seconds:
                since = self._candidate_since
                event = {
                    "type": EVENT_FREED, "table_id": self.table_id, "t": since,
                    "people_count": self._last_people, "duration": since - self.occupied_since,
                }
                self.status, self.occupied_since, self._candidate_since = FREE, None, None
                return event
        return None


@dataclass
class EventLog:
    events: list[dict] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)  # ocupaciones completadas
    _open: dict = field(default_factory=dict)

    def add(self, event: dict):
        self.events.append(event)
        tid = event["table_id"]
        if event["type"] == EVENT_OCCUPIED:
            self._open[tid] = event["t"]
        elif tid in self._open:
            start = self._open.pop(tid)
            self.sessions.append({"table_id": tid, "start": start, "end": event["t"], "duration": event["t"] - start})


class TableEngine:
    """Conjunto de mesas + log. Recibe posiciones de personas ya asignadas a mesas."""

    def __init__(self, occupy_seconds: float, free_seconds: float):
        self.occupy_seconds, self.free_seconds = occupy_seconds, free_seconds
        self.tables: dict[str, TableState] = {}
        self.log = EventLog()

    def sync_tables(self, table_ids: list[str]):
        for tid in table_ids:
            self.tables.setdefault(tid, TableState(tid, self.occupy_seconds, self.free_seconds))
        for tid in list(self.tables):
            if tid not in table_ids:
                del self.tables[tid]

    def update(self, t: float, counts: dict[str, int]):
        for tid, table in self.tables.items():
            event = table.update(t, counts.get(tid, 0))
            if event:
                self.log.add(event)

    def stats(self, now: float) -> dict:
        total = len(self.tables)
        occupied = sum(1 for tb in self.tables.values() if tb.status == OCCUPIED)
        durations = [s["duration"] for s in self.log.sessions]
        if not durations:  # sin ocupaciones cerradas: usar las que están en curso
            durations = [now - tb.occupied_since for tb in self.tables.values() if tb.occupied_since is not None]
        return {
            "total": total,
            "occupied": occupied,
            "free": total - occupied,
            "occupancy_pct": round(100 * occupied / total, 1) if total else 0.0,
            "avg_duration": sum(durations) / len(durations) if durations else 0.0,
        }
