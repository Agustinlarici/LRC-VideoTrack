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

from . import alerts as alerts_mod
from .alerts import Alert
from .service_monitor import FoodMonitor, VisitDetector

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
    free_since: float | None = None     # desde cuándo está libre (None hasta el primer frame)
    first_visit_t: float | None = None  # primera visita de personal de esta ocupación
    visit_count: int = 0
    served_t: float | None = None       # cuándo se detectó comida/bebida servida
    _samples: deque = field(default_factory=deque)  # (t, count) dentro de la ventana
    _last_people: int = 0  # última cantidad > 0 vista mientras estaba ocupada

    def update(self, t: float, count: int) -> dict | None:
        """Procesa el conteo de un frame. Devuelve un evento si hubo transición."""
        self.people_count = count
        if self.free_since is None and self.status == FREE:
            self.free_since = t  # mesa libre desde que empezamos a verla
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
            self.free_since, self.first_visit_t, self.visit_count, self.served_t = None, None, 0, None
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
            self.free_since = left
            self._samples.clear()
            return event
        return None


EVENT_VISIT = "TABLE_STAFF_VISIT"
EVENT_SERVED = "TABLE_SERVED"
EVENT_ALERT = "ALERT"


@dataclass
class EventLog:
    events: list[dict] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)  # ocupaciones completadas
    _open: dict = field(default_factory=dict)

    def add(self, event: dict):
        self.events.append(event)


class TableEngine:
    """Conjunto de mesas + log. Recibe personas/objetos ya asignados a mesas.

    `on_event(event)` se llama con cada evento nuevo (ocupada, libre, visita, servicio, aviso)."""

    def __init__(self, occupy_seconds: float, free_seconds: float, get_settings=None, on_event=None):
        self.occupy_seconds, self.free_seconds = occupy_seconds, free_seconds
        self.get_settings = get_settings or (lambda: {})
        self.on_event = on_event
        self.tables: dict[str, TableState] = {}
        self.visits: dict[str, VisitDetector] = {}
        self.food: dict[str, FoodMonitor] = {}
        self.log = EventLog()
        self.active_alerts: dict[str, Alert] = {}
        self._fired: set[str] = set()
        self.last_t = 0.0
        self.history: list[tuple[float, int, int]] = []  # (t, ocupadas, total), 1 punto cada ~2 s

    def sync_tables(self, table_ids: list[str]):
        for tid in table_ids:
            if tid not in self.tables:
                self.tables[tid] = TableState(tid, self.occupy_seconds, self.free_seconds)
                self.visits[tid], self.food[tid] = VisitDetector(), FoodMonitor()
        for tid in list(self.tables):
            if tid not in table_ids:
                for d in (self.tables, self.visits, self.food):
                    del d[tid]

    def _emit(self, event: dict):
        self.log.add(event)
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:  # noqa: BLE001 - un aviso fallido nunca debe parar el procesamiento
                pass

    def update(self, t: float, counts: dict[str, int], tracks: dict[str, list] = None,
               items: dict[str, int] = None):
        """`tracks`: {mesa: [(track_id, walked_in)]}.  `items`: {mesa: nº objetos} o None si en este
        frame no se detectaron objetos."""
        self.last_t = t
        tracks = tracks or {}
        for tid, table in self.tables.items():
            food, visits = self.food[tid], self.visits[tid]
            if items is not None:
                food.add_sample(t, items.get(tid, 0))

            event = table.update(t, counts.get(tid, 0))
            if event:
                self._emit(event)
                if event["type"] == EVENT_OCCUPIED:
                    food.begin_occupancy()
                else:
                    food.end_occupancy()
                    self.log.sessions.append({
                        "table_id": tid, "start": table.occupied_since if table.occupied_since is not None
                        else event["t"] - event["duration"], "end": event["t"], "duration": event["duration"],
                        "visits": table.visit_count,
                        "service_delay": None if table.served_t is None else table.served_t - (event["t"] - event["duration"]),
                    })

            for visit in visits.update(t, tracks.get(tid, [])):
                # sólo cuenta si la mesa estaba ocupada cuando llegó la persona
                if table.occupied_since is not None and visit["t"] >= table.occupied_since:
                    table.visit_count += 1
                    if table.first_visit_t is None:
                        table.first_visit_t = visit["t"]
                    self._emit({"type": EVENT_VISIT, "table_id": tid, "t": visit["t"],
                                "people_count": table.people_count, "duration": visit["duration"]})

            if table.status == OCCUPIED and table.served_t is None:
                served = food.served_at(t)
                if served is not None and served >= (table.occupied_since or 0):
                    table.served_t = served
                    self._emit({"type": EVENT_SERVED, "table_id": tid, "t": served,
                                "people_count": table.people_count,
                                "after": served - table.occupied_since})

        if not self.history or t - self.history[-1][0] >= 2.0:
            self.history.append((t, sum(1 for tb in self.tables.values() if tb.status == OCCUPIED), len(self.tables)))
            if len(self.history) > 20000:
                del self.history[::2]  # decimar: nunca crece sin límite
        self._update_alerts(t)

    def _update_alerts(self, t: float):
        active = {a.key: a for a in alerts_mod.evaluate(self.tables, t, self.get_settings())}
        self.active_alerts = active
        for key, alert in active.items():
            if key not in self._fired:
                self._fired.add(key)
                self._emit({"type": EVENT_ALERT, "alert": alert.type, "table_id": alert.table_id,
                            "t": t, "people_count": self.tables[alert.table_id].people_count,
                            "message": alert.message})

    def stats(self, now: float) -> dict:
        total = len(self.tables)
        occupied = sum(1 for tb in self.tables.values() if tb.status == OCCUPIED)
        durations = [s["duration"] for s in self.log.sessions]
        if not durations:  # sin ocupaciones cerradas: usar las que están en curso
            durations = [now - tb.occupied_since for tb in self.tables.values() if tb.occupied_since is not None]
        delays = [s["service_delay"] for s in self.log.sessions if s["service_delay"] is not None]
        delays += [tb.served_t - tb.occupied_since for tb in self.tables.values()
                   if tb.occupied_since is not None and tb.served_t is not None]
        return {
            "total": total,
            "occupied": occupied,
            "free": total - occupied,
            "occupancy_pct": round(100 * occupied / total, 1) if total else 0.0,
            "avg_duration": sum(durations) / len(durations) if durations else 0.0,
            "avg_service_delay": sum(delays) / len(delays) if delays else None,
            "visits": sum(1 for e in self.log.events if e["type"] == EVENT_VISIT),
            "active_alerts": len(self.active_alerts),
        }
