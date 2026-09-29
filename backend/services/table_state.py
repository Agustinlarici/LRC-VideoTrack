"""Lógica de negocio: estado de cada mesa con debounce y registro de eventos.

Trabaja en segundos de vídeo (`t`), sin saber nada de YOLO ni de OpenCV.

El debounce usa una ventana deslizante en vez de "N segundos seguidos", porque YOLO parpadea
(un frame sin detección no debe reiniciar la cuenta):

    LIBERA   --(en los últimos occupy_seconds hubo gente en >= 80% de los frames)--> OCCUPATA
    OCCUPATA --(en los últimos free_seconds hubo gente en <= 10% de los frames)---> LIBERA

El timestamp del evento es el instante en que empezó el cambio (no el de la confirmación),
para que la hora de ocupación sea la real.
"""
from collections import deque
from dataclasses import dataclass, field

FREE = "LIBERA"
OCCUPIED = "OCCUPATA"

EVENT_OCCUPIED = "TABLE_OCCUPIED"
EVENT_FREED = "TABLE_FREED"

OCCUPY_MIN_RATIO = 0.8   # fracción mínima de frames con gente para ocupar
FREE_MAX_RATIO = 0.1     # fracción máxima de frames con gente para liberar


@dataclass
class TableState:
    table_id: str
    occupy_seconds: float
    free_seconds: float
    status: str = FREE
    people_count: int = 0
    occupied_since: float | None = None
    _samples: deque = field(default_factory=deque)  # (t, count) dentro de la ventana
    _last_people: int = 0  # última cantidad > 0 vista mientras estaba ocupada

    def update(self, t: float, count: int) -> dict | None:
        """Procesa el conteo de un frame. Devuelve un evento si hubo transición."""
        self.people_count = count
        if self.status == OCCUPIED and count > 0:
            self._last_people = count

        window = self.occupy_seconds if self.status == FREE else self.free_seconds
        self._samples.append((t, count))
        # Descarta lo viejo, pero conserva una muestra en/antes del borde para medir bien el span
        while len(self._samples) > 1 and self._samples[1][0] <= t - window:
            self._samples.popleft()
        if t - self._samples[0][0] < window:
            return None  # todavía no hay historia suficiente

        present = [(ts, c) for ts, c in self._samples if c > 0]
        ratio = len(present) / len(self._samples)

        if self.status == FREE and ratio >= OCCUPY_MIN_RATIO:
            since, peak = present[0][0], max(c for _, c in present)
            self.status, self.occupied_since, self._last_people = OCCUPIED, since, peak
            self._samples.clear()
            return {"type": EVENT_OCCUPIED, "table_id": self.table_id, "t": since, "people_count": peak}

        if self.status == OCCUPIED and ratio <= FREE_MAX_RATIO:
            # Momento en que dejó de haber gente: la muestra siguiente a la última con gente
            left = self._samples[0][0]
            if present:
                last = present[-1][0]
                left = next(ts for ts, _ in self._samples if ts > last) if last < t else t
            left = max(left, self.occupied_since)
            event = {
                "type": EVENT_FREED, "table_id": self.table_id, "t": left,
                "people_count": self._last_people, "duration": left - self.occupied_since,
            }
            self.status, self.occupied_since = FREE, None
            self._samples.clear()
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
