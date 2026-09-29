"""Orquesta: fuente -> YOLO/ByteTrack -> zonas -> motor de mesas -> frame anotado.

Corre en un hilo. El API sólo lee `snapshot()` y `latest_jpeg`.
"""
import threading
import time
from datetime import datetime, timedelta

import cv2

from .. import config
from ..vision.annotator import annotate
from ..vision.detector import PersonTracker
from ..vision.video_source import VideoSource
from .table_state import TableEngine
from .zones import ZoneStore, point_in_polygon, to_pixels


def parse_clock(text: str | None) -> datetime:
    """'20:00' o '20:00:00' -> datetime de hoy a esa hora. Sin valor: ahora."""
    now = datetime.now()
    if not text:
        return now
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            hh = datetime.strptime(text.strip(), fmt)
            return now.replace(hour=hh.hour, minute=hh.minute, second=hh.second, microsecond=0)
        except ValueError:
            continue
    raise ValueError("La hora de inicio debe tener formato HH:MM o HH:MM:SS")


class Pipeline:
    def __init__(self, zones: ZoneStore):
        self.zones = zones
        self._tracker: PersonTracker | None = None  # se crea al primer uso (carga el modelo)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._tracker_lock = threading.Lock()

        self.status = "idle"  # idle | loading | running | finished | error
        self.error: str | None = None
        self.run_id = 0
        self.source = ""
        self.clock_start = datetime.now()
        self.video_t = 0.0
        self.progress = 0.0
        self.engine = TableEngine(config.OCCUPY_SECONDS, config.FREE_SECONDS)
        self.people_tracks = 0
        self.latest_jpeg: bytes | None = None
        self.frame_id = 0

    # ---------- control ----------
    def start(self, source: str, start_time: str | None, occupy_seconds: float, free_seconds: float, realtime: bool):
        clock_start = parse_clock(start_time)  # valida antes de tocar nada
        self.stop()
        with self._lock:
            self.run_id += 1
            run_id = self.run_id
            self.source, self.clock_start = source, clock_start
            self.status, self.error = "loading", None
            self.video_t, self.progress, self.people_tracks = 0.0, 0.0, 0
            self.latest_jpeg, self.frame_id = None, 0
            self.engine = TableEngine(occupy_seconds, free_seconds)
            self._stop = threading.Event()  # un evento por ejecución: un hilo viejo nunca afecta al nuevo
            self._thread = threading.Thread(
                target=self._run, args=(run_id, self._stop, self.engine, source, realtime), daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=10)
        with self._lock:
            if self.status in ("running", "loading"):
                self.status = "idle"

    def _current(self, run_id: int) -> bool:
        return self.run_id == run_id

    def _set_status(self, run_id: int, status: str, error: str | None = None):
        with self._lock:
            if self._current(run_id):
                self.status, self.error = status, error

    # ---------- hilo principal ----------
    def _run(self, run_id: int, stop: threading.Event, engine: TableEngine, source_name: str, realtime: bool):
        source = None
        try:
            with self._tracker_lock:
                if self._tracker is None:
                    self._tracker = PersonTracker()
            if stop.is_set():
                return
            self._tracker.reset()
            source = VideoSource(source_name, config.PROCESS_FPS)
            self._set_status(run_id, "running")

            wall_start = time.time()
            zone_version, polygons = -1, {}

            while not stop.is_set():
                frame = source.read()
                if frame is None:
                    self._set_status(run_id, "finished")
                    break

                # Ritmo de reproducción a velocidad real (sólo para archivos)
                if realtime and not source.live:
                    ahead = frame.t - (time.time() - wall_start)
                    if ahead > 0:
                        stop.wait(ahead)
                        if stop.is_set():
                            break

                if self.zones.version != zone_version:
                    zone_version = self.zones.version
                    polygons = {z["id"]: to_pixels(z, source.width, source.height) for z in self.zones.get()}
                    engine.sync_tables(list(polygons))

                people = self._tracker.track(frame.image)

                counts = {tid: 0 for tid in polygons}
                for p in people:
                    c = p.center
                    for tid, poly in polygons.items():
                        if point_in_polygon(c, poly):
                            counts[tid] += 1
                            break  # una persona pertenece a una sola mesa

                engine.update(frame.t, counts)

                view = annotate(frame.image, people, [
                    {"id": tid, "polygon": polygons[tid], "status": tb.status, "people_count": counts.get(tid, 0)}
                    for tid, tb in engine.tables.items() if tid in polygons
                ])
                if stop.is_set() or not self._current(run_id):
                    break
                self._publish(view, frame, source, len(people))
        except Exception as exc:  # noqa: BLE001 - mostramos el error en el dashboard
            self._set_status(run_id, "error", f"{type(exc).__name__}: {exc}")
        finally:
            if source:
                source.close()

    def _publish(self, view, frame, source, n_people):
        h, w = view.shape[:2]
        if w > config.STREAM_MAX_WIDTH:
            view = cv2.resize(view, (config.STREAM_MAX_WIDTH, int(h * config.STREAM_MAX_WIDTH / w)))
        ok, buf = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, config.STREAM_JPEG_QUALITY])
        if not ok:
            return
        self.video_t = frame.t
        self.people_tracks = n_people
        self.progress = frame.index / source.total_frames if source.total_frames else 0.0
        self.latest_jpeg = buf.tobytes()
        self.frame_id += 1

    # ---------- lectura para el API ----------
    def _clock(self, t: float) -> str:
        return (self.clock_start + timedelta(seconds=t)).strftime("%H:%M:%S")

    def snapshot(self) -> dict:
        t = self.video_t
        engine = self.engine
        tables = []
        for z in self.zones.get():
            tb = engine.tables.get(z["id"])
            occupied = tb is not None and tb.occupied_since is not None
            tables.append({
                "id": z["id"],
                "status": tb.status if tb else "LIBERA",
                "people_count": tb.people_count if tb else 0,
                "occupied_since": self._clock(tb.occupied_since) if occupied else None,
                "duration": (t - tb.occupied_since) if occupied else 0.0,
            })
        events = [{
            "type": e["type"], "table_id": e["table_id"], "people_count": e["people_count"],
            "time": self._clock(e["t"]), "duration": e.get("duration"),
        } for e in engine.log.events]
        return {
            "status": self.status, "error": self.error, "run_id": self.run_id, "source": self.source,
            "clock": self._clock(t), "video_seconds": t, "progress": self.progress,
            "people_visible": self.people_tracks,
            "tables": tables, "stats": engine.stats(t), "events": events[::-1],
        }
