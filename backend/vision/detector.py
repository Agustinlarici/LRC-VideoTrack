"""YOLO + ByteTrack para personas, y detección de objetos (comida/bebida) a baja frecuencia."""
from dataclasses import dataclass

from .. import config


@dataclass
class Person:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass
class Item:
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


def _ceil32(n: int) -> int:
    return -(-int(n) // 32) * 32


class PersonTracker:
    def __init__(self):
        from ultralytics import YOLO  # import diferido: arranque del API más rápido

        self.model = YOLO(config.YOLO_MODEL)

    def reset(self):
        """Reinicia el estado del tracker (al empezar un vídeo nuevo o cambiar la región)."""
        predictor = getattr(self.model, "predictor", None)
        if predictor is not None and getattr(predictor, "trackers", None):
            for tr in predictor.trackers:
                tr.reset()

    def track(self, image, roi=None) -> list[Person]:
        """Personas con ID. `roi` = (x1, y1, x2, y2): sólo se analiza esa región, con la resolución
        adaptada a su tamaño (así en cámaras HD/4K las personas lejanas no se pierden al reducir).
        Las coordenadas devueltas son siempre del frame completo."""
        ox = oy = 0
        if roi is not None and (roi[2] - roi[0] < 32 or roi[3] - roi[1] < 32):
            roi = None  # región degenerada (mesa dibujada casi como una línea): analiza el frame completo
        if roi is not None:
            ox, oy, x2, y2 = roi
            image = image[oy:y2, ox:x2]
        h, w = image.shape[:2]
        imgsz = min(max(_ceil32(max(w, h)), config.YOLO_IMGSZ), max(config.MAX_IMGSZ, config.YOLO_IMGSZ))

        results = self.model.track(
            image,
            persist=True,
            tracker=config.TRACKER,
            classes=[config.PERSON_CLASS_ID],
            conf=config.TRACK_MIN_CONF,  # bajo a propósito: ByteTrack decide qué baja confianza aprovechar
            iou=config.YOLO_IOU,
            imgsz=imgsz,
            verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return []
        people = []
        for (x1, y1, x2, y2), tid, conf in zip(boxes.xyxy.tolist(), boxes.id.int().tolist(), boxes.conf.tolist()):
            people.append(Person(int(tid), x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(conf)))
        return people


class ItemDetector:
    """Detecta platos/vasos/comida sin tracking. Usa su PROPIA instancia del modelo para no
    mezclar sus detecciones con el estado del tracker de personas.

    Analiza un recorte por mesa (en una sola llamada por lotes): los objetos pequeños quedan mucho
    más grandes que en el frame completo y se detectan bastante mejor (p. ej. platos)."""

    def __init__(self):
        from ultralytics import YOLO

        self.model = YOLO(config.ITEM_MODEL)

    def detect(self, image, rects: dict[str, tuple] | None = None) -> dict[str, list[Item]]:
        """`rects`: {mesa: (x1, y1, x2, y2)}. Sin `rects` analiza el frame completo (clave "").
        Devuelve {mesa: [Item]} con coordenadas del frame completo."""
        if not rects:
            rects = {"": (0, 0, image.shape[1], image.shape[0])}
        rects = {tid: r for tid, r in rects.items() if r[2] - r[0] >= 16 and r[3] - r[1] >= 16}
        if not rects:
            return {}
        ids = list(rects)
        crops = [image[r[1]:r[3], r[0]:r[2]] for r in rects.values()]
        results = self.model.predict(
            crops,
            classes=config.ITEM_CLASS_IDS,
            conf=config.ITEM_CONF,
            imgsz=config.ITEM_IMGSZ,
            verbose=False,
        )
        out: dict[str, list[Item]] = {}
        for tid, res, rect in zip(ids, results, rects.values()):
            ox, oy = rect[0], rect[1]
            items = []
            if res.boxes is not None and len(res.boxes):
                for (x1, y1, x2, y2), c, conf in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
                    items.append(Item(res.names[int(c)], x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(conf)))
            out[tid] = items
        return out
