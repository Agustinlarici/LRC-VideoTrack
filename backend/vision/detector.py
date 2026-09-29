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


class PersonTracker:
    def __init__(self):
        from ultralytics import YOLO  # import diferido: arranque del API más rápido

        self.model = YOLO(config.YOLO_MODEL)

    def reset(self):
        """Reinicia el estado del tracker (al empezar un vídeo nuevo)."""
        predictor = getattr(self.model, "predictor", None)
        if predictor is not None and getattr(predictor, "trackers", None):
            for tr in predictor.trackers:
                tr.reset()

    def track(self, image) -> list[Person]:
        results = self.model.track(
            image,
            persist=True,
            tracker=config.TRACKER,
            classes=[config.PERSON_CLASS_ID],
            conf=config.YOLO_CONF,
            imgsz=config.YOLO_IMGSZ,
            verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return []
        people = []
        for xyxy, tid, conf in zip(boxes.xyxy.tolist(), boxes.id.int().tolist(), boxes.conf.tolist()):
            people.append(Person(int(tid), *xyxy, float(conf)))
        return people


class ItemDetector:
    """Detecta platos/vasos/comida sin tracking. Usa su PROPIA instancia del modelo para no
    mezclar sus detecciones con el estado del tracker de personas."""

    def __init__(self):
        from ultralytics import YOLO

        self.model = YOLO(config.ITEM_MODEL)

    def detect(self, image) -> list[Item]:
        results = self.model.predict(
            image,
            classes=config.ITEM_CLASS_IDS,
            conf=config.ITEM_CONF,
            imgsz=config.ITEM_IMGSZ,
            verbose=False,
        )
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return []
        names = results[0].names
        return [
            Item(names[int(c)], *xyxy, float(conf))
            for xyxy, c, conf in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist())
        ]
