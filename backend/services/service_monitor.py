"""Servicio a la mesa (estimado): visitas de personal y comida/bebida servida.

Lógica pura (sin OpenCV ni YOLO). Son HEURÍSTICAS, no reconocimiento:

  Visita de personal  = una persona que ENTRA andando desde fuera de la mesa, se queda entre
                        VISIT_MIN y VISIT_MAX segundos y se va. Quien ya estaba dentro cuando
                        se le detectó por primera vez (comensal que reaparece con otro ID) no cuenta.
  Comida/bebida       = el número de objetos (platos, copas, comida...) sobre la mesa sube al menos 1
                        respecto al que había al sentarse, de forma sostenida.
"""
from collections import Counter, deque
from statistics import median

from .. import config


class VisitDetector:
    """Una por mesa. Recibe cada frame las personas dentro de la mesa."""

    def __init__(self, min_seconds: float = None, max_seconds: float = None, leave_grace: float = None):
        self.min_s = config.VISIT_MIN_SECONDS if min_seconds is None else min_seconds
        self.max_s = config.VISIT_MAX_SECONDS if max_seconds is None else max_seconds
        self.grace = config.VISIT_LEAVE_GRACE if leave_grace is None else leave_grace
        self._tracks: dict[int, dict] = {}

    def update(self, t: float, tracks: list[tuple[int, bool]]) -> list[dict]:
        """`tracks`: [(track_id, walked_in)] de las personas dentro de la mesa en este frame.
        Devuelve visitas terminadas: [{"t": inicio, "duration": segundos}]."""
        seen = set()
        for tid, walked_in in tracks:
            seen.add(tid)
            info = self._tracks.get(tid)
            if info is None:
                self._tracks[tid] = {"first": t, "last": t, "walked_in": walked_in}
            else:
                info["last"] = t

        visits = []
        for tid in list(self._tracks):
            info = self._tracks[tid]
            if tid in seen or t - info["last"] <= self.grace:
                continue
            del self._tracks[tid]
            dwell = info["last"] - info["first"]
            if info["walked_in"] and self.min_s <= dwell <= self.max_s:
                visits.append({"t": info["first"], "duration": dwell})
        return visits

    def residents(self, t: float) -> int:
        """Personas sentadas: las que ya estaban en la mesa al verlas por primera vez, o llevan más de
        VISIT_MAX segundos. Excluye al personal que está de visita (así no infla el tamaño del grupo)."""
        return sum(1 for info in self._tracks.values()
                   if t - info["last"] <= self.grace and (not info["walked_in"] or t - info["first"] > self.max_s))

    def reset(self):
        self._tracks.clear()


class FoodMonitor:
    """Una por mesa. Recibe el nº de objetos sobre la mesa (a baja frecuencia)."""

    def __init__(self, confirm_seconds: float = None):
        self.confirm = config.SERVICE_CONFIRM_SECONDS if confirm_seconds is None else confirm_seconds
        self._samples: deque[tuple[float, int]] = deque()
        self.baseline: int | None = None

    def add_sample(self, t: float, n_items: int):
        self._samples.append((t, n_items))
        # guarda ~2x la ventana de confirmación (sirve para calcular la base al sentarse)
        while self._samples and self._samples[0][0] < t - max(2 * self.confirm, 6.0):
            self._samples.popleft()

    def begin_occupancy(self):
        """Fija la base: objetos que ya había sobre la mesa al sentarse (copas, cubiertos...)."""
        counts = [n for _, n in self._samples]
        self.baseline = round(median(counts)) if counts else 0

    def end_occupancy(self):
        self.baseline = None

    def served_at(self, t: float) -> float | None:
        """Instante en que empezó el servicio si los objetos SOSTENIDOS superan la base."""
        if self.baseline is None or not self._samples:
            return None
        window = [(ts, n) for ts, n in self._samples if ts >= t - self.confirm]
        if len(window) < 2 or t - window[0][0] < self.confirm * 0.8:
            return None
        if median(n for _, n in window) >= self.baseline + 1:
            return next(ts for ts, n in window if n >= self.baseline + 1)
        return None


    def cleared_at(self, t: float) -> float | None:
        """Mesa recogida: tras el servicio, los objetos SOSTENIDOS vuelven a la base (se llevaron platos y vasos)."""
        if self.baseline is None or not self._samples:
            return None
        window = [(ts, n) for ts, n in self._samples if ts >= t - self.confirm]
        if len(window) < 2 or t - window[0][0] < self.confirm * 0.8:
            return None
        if median(n for _, n in window) <= self.baseline:
            return window[0][0]
        return None


class PartyTracker:
    """Tamaño del grupo sentado (APROXIMADO): mediana de personas en la mesa; emite cuando cambia de
    forma estable (llegan más comensales o se levantan algunos)."""

    def __init__(self, window: float = 6.0):
        self.window = window
        self._samples: deque[tuple[float, int]] = deque()
        self.size: int | None = None

    def begin(self, size: int):
        self.size = size
        self._samples.clear()

    def reset(self):
        self.size = None
        self._samples.clear()

    def update(self, t: float, count: int) -> dict | None:
        if self.size is None:
            return None
        self._samples.append((t, count))
        while len(self._samples) > 1 and self._samples[1][0] <= t - self.window:
            self._samples.popleft()
        if t - self._samples[0][0] < self.window:
            return None
        counts = [c for _, c in self._samples]
        half = [c for ts, c in self._samples if ts >= t - self.window / 2]
        full_m, half_m = round(median(counts)), round(median(half))
        if full_m == half_m and full_m > 0 and full_m != self.size:
            prev, self.size = self.size, full_m
            self._samples.clear()
            return {"prev": prev, "people_count": full_m}
        return None


class ItemsTracker:
    """Objetos sobre la mesa suavizados (mediana de las últimas 5 detecciones); emite cuando cambia."""

    def __init__(self):
        self._recent: deque[list[str]] = deque(maxlen=5)
        self.count: int | None = None

    def update(self, names: list[str]) -> dict | None:
        self._recent.append(names)
        if len(self._recent) < 5:
            return None
        value = round(median(len(n) for n in self._recent))
        if self.count is None:
            self.count = value
            return None
        if value != self.count:
            prev, self.count = self.count, value
            latest = max(self._recent, key=len)
            return {"items": value, "prev_items": prev, "names": dict(Counter(latest))}
        return None
