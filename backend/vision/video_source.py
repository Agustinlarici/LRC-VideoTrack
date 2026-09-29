"""Fuente de vídeo. Para pasar de MP4 a RTSP basta con cambiar el string `source`."""
import time
from dataclasses import dataclass

import cv2
import numpy as np


def is_live(source: str) -> bool:
    return source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))


@dataclass
class Frame:
    image: np.ndarray
    t: float  # segundos desde el inicio (reloj del vídeo, o reloj real si es live)
    index: int


class VideoSource:
    def __init__(self, source: str):
        self.source = source
        self.live = is_live(source)
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente de vídeo: {source}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 1 else 25.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not self.live else 0
        self._index = 0
        self._t0 = time.time()

    def read(self) -> Frame | None:
        ok, image = self.cap.read()
        if not ok:
            return None
        t = (time.time() - self._t0) if self.live else self._index / self.fps
        frame = Frame(image=image, t=t, index=self._index)
        self._index += 1
        return frame

    def close(self):
        self.cap.release()


def grab_first_frame(source: str) -> np.ndarray | None:
    """Un frame suelto (para dibujar las mesas). No se guarda en disco."""
    cap = cv2.VideoCapture(source)
    try:
        ok, image = cap.read()
        return image if ok else None
    finally:
        cap.release()
