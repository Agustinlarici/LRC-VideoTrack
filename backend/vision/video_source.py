"""Fuente de vídeo. Acepta:

  - una ruta a un archivo (MP4...)      -> se procesa a su ritmo, reloj = frame/fps
  - rtsp://... / http://... (cámara IP) -> en directo, con reconexión automática
  - un número ("0", "1")                -> webcam USB, en directo

En directo un hilo lee siempre el último frame (si YOLO va más lento se descartan frames en vez
de acumular retraso) y el reloj es el tiempo real transcurrido.
"""
import os
import threading
import time
from dataclasses import dataclass

# TCP es mucho más estable que UDP para RTSP. Debe fijarse antes de abrir la primera captura.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

NO_FRAME = object()  # en directo: todavía no llegó un frame nuevo (o se está reconectando)


def is_live(source: str) -> bool:
    s = source.strip().lower()
    return s.isdigit() or s.startswith(("rtsp://", "rtsps://", "rtmp://", "http://", "https://"))


def _open(source: str) -> cv2.VideoCapture:
    if source.strip().isdigit():
        index = int(source)
        return cv2.VideoCapture(index, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(index)
    return cv2.VideoCapture(source)


@dataclass
class Frame:
    image: np.ndarray
    t: float  # segundos desde el inicio (reloj del vídeo, o reloj real si es directo)
    index: int


class VideoSource:
    def __init__(self, source: str, process_fps: float = 0):
        self.source = source.strip()
        self.live = is_live(self.source)
        self.cap = _open(self.source)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente de vídeo: {source}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and 1 < fps < 121 else 25.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) if not self.live else 0
        self.connected = True
        self._index = 0
        self._t0 = time.time()

        if self.live:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.stride = 1
            self._closed = threading.Event()
            self._cond = threading.Condition()
            self._latest: np.ndarray | None = None
            self._seq = 0
            self._served_seq = 0
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
        else:
            # Sólo se procesa 1 de cada `stride` frames; los demás se saltan con grab() (barato)
            self.stride = max(1, round(self.fps / process_fps)) if process_fps else 1

    # ---------- directo: hilo lector con reconexión ----------
    def _reader(self):
        failures = 0
        while not self._closed.is_set():
            ok, image = self.cap.read() if self.cap.isOpened() else (False, None)
            if ok:
                failures = 0
                self.connected = True
                with self._cond:
                    self._latest, self._seq = image, self._seq + 1
                    self._cond.notify_all()
                continue
            failures += 1
            if failures >= 3:  # cámara caída: reintentar abrir con espera creciente
                self.connected = False
                self.cap.release()
                if self._closed.wait(min(2.0 * failures, 10.0)):
                    return
                self.cap = _open(self.source)
                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                time.sleep(0.05)

    def read(self):
        """Frame | None (fin del archivo) | NO_FRAME (sólo en directo, sin frame nuevo aún)."""
        if self.live:
            with self._cond:
                if not self._cond.wait_for(lambda: self._seq != self._served_seq, timeout=1.0):
                    return NO_FRAME
                self._served_seq = self._seq
                image = self._latest
            frame = Frame(image=image, t=time.time() - self._t0, index=self._index)
            self._index += 1
            return frame

        ok, image = self.cap.read()
        if not ok:
            return None
        frame = Frame(image=image, t=self._index / self.fps, index=self._index)
        for _ in range(self.stride - 1):
            if not self.cap.grab():
                break
        self._index += self.stride
        return frame

    def close(self):
        if self.live:
            self._closed.set()
            self._thread.join(timeout=3)
        self.cap.release()


def grab_first_frame(source: str, attempts: int = 40) -> np.ndarray | None:
    """Un frame suelto (para dibujar las mesas). No se guarda en disco.
    En directo hacen falta varios intentos: las primeras lecturas suelen fallar."""
    cap = _open(source.strip())
    try:
        for _ in range(attempts if is_live(source) else 1):
            ok, image = cap.read()
            if ok:
                return image
            time.sleep(0.1)
        return None
    finally:
        cap.release()
