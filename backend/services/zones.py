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
