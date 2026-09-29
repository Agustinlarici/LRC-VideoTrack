"""Reglas de avisos. Lógica pura: recibe el estado de las mesas y los umbrales."""
from dataclasses import dataclass

UNATTENDED = "UNATTENDED"      # ocupada sin visita de personal
SERVICE_SLOW = "SERVICE_SLOW"  # ocupada sin comida/bebida servida
LONG_STAY = "LONG_STAY"        # ocupación larga
FREE_IDLE = "FREE_IDLE"        # libre sin volver a ocuparse


def _min(seconds: float) -> str:
    return f"{int(seconds // 60)} min" if seconds >= 60 else f"{int(seconds)} s"


@dataclass(frozen=True)
class Alert:
    key: str
    type: str
    table_id: str
    message: str
    since: float  # instante (segundos de vídeo) en que se cumplió la condición


def evaluate(tables: dict, t: float, cfg: dict) -> list[Alert]:
    """`tables`: {id: TableState}. `cfg`: umbrales en segundos (0 = desactivado)."""
    out = []
    for tid, tb in tables.items():
        if tb.occupied_since is not None:
            elapsed = t - tb.occupied_since
            ep = f"{tid}:{tb.occupied_since}"  # identifica esta ocupación (para avisar una vez por ocupación)
            limit = cfg.get("unattended_seconds", 0)
            if limit and tb.first_visit_t is None and elapsed >= limit:
                out.append(Alert(f"{UNATTENDED}:{ep}", UNATTENDED, tid,
                                 f"{tid} lleva {_min(elapsed)} ocupada sin visita del personal", tb.occupied_since + limit))
            limit = cfg.get("service_seconds", 0)
            if limit and tb.served_t is None and elapsed >= limit:
                out.append(Alert(f"{SERVICE_SLOW}:{ep}", SERVICE_SLOW, tid,
                                 f"{tid} lleva {_min(elapsed)} sin que se sirva comida o bebida", tb.occupied_since + limit))
            limit = cfg.get("long_stay_seconds", 0)
            if limit and elapsed >= limit:
                out.append(Alert(f"{LONG_STAY}:{ep}", LONG_STAY, tid,
                                 f"{tid} lleva {_min(elapsed)} ocupada", tb.occupied_since + limit))
        else:
            limit = cfg.get("free_idle_seconds", 0)
            if limit and tb.free_since is not None and t - tb.free_since >= limit:
                out.append(Alert(f"{FREE_IDLE}:{tid}:{tb.free_since}", FREE_IDLE, tid,
                                 f"{tid} lleva {_min(t - tb.free_since)} libre", tb.free_since + limit))
    return out
