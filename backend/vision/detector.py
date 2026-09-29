"""YOLO + ByteTrack: devuelve personas con ID de tracking persistente."""
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
