"""Zonas de mesas: persistencia en JSON y geometría.

Los puntos se guardan NORMALIZADOS (0..1) para no depender de la resolución del vídeo.
"""
import json
import threading

import cv2
import numpy as np

from .. import config


class ZoneStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.version = 0
        self._zones: list[dict] = []
        if config.ZONES_FILE.exists():
            self._zones = json.loads(config.ZONES_FILE.read_text(encoding="utf-8")).get("zones", [])

    def get(self) -> list[dict]:
        with self._lock:
            return [dict(z) for z in self._zones]

    def save(self, zones: list[dict]) -> list[dict]:
        clean = []
        seen = set()
        for z in zones:
            zid = str(z["id"]).strip().upper()
            pts = [[min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)] for x, y in z["points"]]
            if not zid or zid in seen or len(pts) < 3:
                continue
            seen.add(zid)
            clean.append({"id": zid, "points": pts})
        with self._lock:
            self._zones = clean
            self.version += 1
            config.ZONES_FILE.write_text(json.dumps({"zones": clean}, indent=2), encoding="utf-8")
        return clean


def to_pixels(zone: dict, width: int, height: int) -> np.ndarray:
    return np.array([[x * width, y * height] for x, y in zone["points"]], dtype=np.int32)


def point_in_polygon(point: tuple[float, float], polygon: np.ndarray) -> bool:
    return cv2.pointPolygonTest(polygon.reshape(-1, 1, 2).astype(np.float32), point, False) >= 0


Rect = tuple[int, int, int, int]  # x1, y1, x2, y2 en píxeles


def bounding_rect(polygon: np.ndarray) -> Rect:
    x1, y1 = polygon.min(axis=0)
    x2, y2 = polygon.max(axis=0)
    return int(x1), int(y1), int(x2), int(y2)


def expand_rect(rect: Rect, margin: float, width: int, height: int) -> Rect:
    """Amplía el rectángulo un `margin` (fracción de su tamaño) sin salirse de la imagen."""
    x1, y1, x2, y2 = rect
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return (int(max(0, x1 - mx)), int(max(0, y1 - my)), int(min(width, x2 + mx)), int(min(height, y2 + my)))


def union_rect(rects: list[Rect]) -> Rect:
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))
