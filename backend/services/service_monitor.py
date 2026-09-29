"""Servicio a la mesa (estimado): visitas de personal y comida/bebida servida.

Lógica pura (sin OpenCV ni YOLO). Son HEURÍSTICAS, no reconocimiento:

  Visita de personal  = una persona que ENTRA andando desde fuera de la mesa, se queda entre
                        VISIT_MIN y VISIT_MAX segundos y se va. Quien ya estaba dentro cuando
                        se le detectó por primera vez (comensal que reaparece con otro ID) no cuenta.
  Comida/bebida       = el número de objetos (platos, copas, comida...) sobre la mesa sube al menos 1
                        respecto al que había al sentarse, de forma sostenida.
"""
from collections import deque
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
