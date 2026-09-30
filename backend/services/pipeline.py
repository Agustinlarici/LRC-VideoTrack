"""Orquesta: fuente -> YOLO/ByteTrack -> zonas -> motor de mesas -> frame anotado.

Corre en un hilo. El API sólo lee `snapshot()` y `latest_jpeg`.
"""
import csv
import io
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta

import cv2

from .. import config
from ..vision.annotator import annotate
from ..vision.detector import ItemDetector, PersonTracker
from ..vision.video_source import NO_FRAME, VideoSource
from .settings import Settings
from .table_state import TableEngine
from .zones import ZoneStore, bounding_rect, expand_rect, point_in_polygon, to_pixels, union_rect


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


def send_webhook(url: str, event: dict):
    """Avisa a un servicio externo (Slack, Telegram vía n8n/Make, etc.) sin bloquear el procesamiento."""
    def _post():
        try:
            req = urllib.request.Request(url, data=json.dumps(event).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5).close()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_post, daemon=True).start()


class Pipeline:
    def __init__(self, zones: ZoneStore, settings: Settings = None, tracker_factory=PersonTracker,
                 item_factory=ItemDetector):
        self.zones = zones
        self.settings = settings or Settings()
        self._tracker_factory, self._item_factory = tracker_factory, item_factory
        self._tracker = None  # se crean al primer uso (cargan el modelo)
        self._items = None
        self.live = False
        self.connected = True
        self.proc_fps = 0.0
        self._last_pub = 0.0
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
        self.engine = TableEngine(config.OCCUPY_SECONDS, config.FREE_SECONDS, self.settings.get)
        self.people_tracks = 0
        self.latest_jpeg: bytes | None = None
        self.frame_id = 0

    # ---------- control ----------
    def start(self, source: str, start_time: str | None, realtime: bool = True):
        clock_start = parse_clock(start_time)  # valida antes de tocar nada
        self.stop()
        with self._lock:
            self.run_id += 1
            run_id = self.run_id
            self.source, self.clock_start = source, clock_start
            self.status, self.error = "loading", None
            self.video_t, self.progress, self.people_tracks = 0.0, 0.0, 0
            self.latest_jpeg, self.frame_id = None, 0
            cfg = self.settings.get()
            self.engine = TableEngine(cfg["occupy_seconds"], cfg["free_seconds"], self.settings.get, self._notify)
            self.live, self.connected = False, True
            self.proc_fps, self._last_pub = 0.0, 0.0
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

    def _notify(self, event: dict):
        url = self.settings.get().get("webhook_url")
        if url:
            send_webhook(url, {**event, "time": self._clock(event["t"]), "source": self.source})

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
                    self._tracker = self._tracker_factory()
                if self._items is None:
                    self._items = self._item_factory()
            if stop.is_set():
                return
            self._tracker.reset()
            source = VideoSource(source_name, config.PROCESS_FPS)
            self.live = source.live
            self._set_status(run_id, "running")

            wall_start = time.time()
            zone_version, polygons = -1, {}
            origins: dict[int, tuple[float, float]] = {}  # dónde se vio por primera vez cada persona
            last_item_t, items, item_gap = -1e9, [], config.ITEM_INTERVAL
            person_roi, table_rects = None, {}

            while not stop.is_set():
                frame = source.read()
                self.connected = source.connected
                if frame is None:
                    self._set_status(run_id, "finished")
                    break
                if frame is NO_FRAME:
                    continue

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
                    table_rects = {tid: expand_rect(bounding_rect(poly), config.ITEM_MARGIN, source.width, source.height)
                                   for tid, poly in polygons.items()}
                    new_roi = None
                    if config.USE_ROI and polygons:
                        new_roi = expand_rect(union_rect([bounding_rect(p) for p in polygons.values()]),
                                              config.ROI_MARGIN, source.width, source.height)
                    if new_roi != person_roi:
                        person_roi = new_roi
                        self._tracker.reset()  # las coordenadas del recorte cambian: los IDs viejos ya no valen

                people = self._tracker.track(frame.image, person_roi)

                # Objetos (comida/bebida) a baja frecuencia
                items_per_table = None
                if polygons and frame.t - last_item_t >= item_gap:
                    last_item_t = frame.t
                    started = time.time()
                    found = self._items.detect(frame.image, table_rects)
                    # cada mesa sólo se queda con los objetos cuyo centro cae DENTRO de su polígono
                    # (así un objeto en el solape de dos recortes no se cuenta dos veces)
                    items, items_per_table = [], {tid: 0 for tid in polygons}
                    for tid, its in found.items():
                        for it in its:
                            if tid in polygons and point_in_polygon(it.center, polygons[tid]):
                                items.append(it)
                                items_per_table[tid] += 1
                    # si el PC va justo, espacia las detecciones para no gastar más de ~25% de CPU en objetos
                    item_gap = max(config.ITEM_INTERVAL, 3 * (time.time() - started))

                counts = {tid: 0 for tid in polygons}
                tracks = {tid: [] for tid in polygons}
                for p in people:
                    c = p.center
                    origin = origins.setdefault(p.track_id, c)
                    for tid, poly in polygons.items():
                        if point_in_polygon(c, poly):
                            counts[tid] += 1
                            # "entró andando" = la primera vez que la vimos estaba fuera de esta mesa
                            tracks[tid].append((p.track_id, not point_in_polygon(origin, poly)))
                            break  # una persona pertenece a una sola mesa

                engine.update(frame.t, counts, tracks, items_per_table)

                view = annotate(frame.image, people, items, [
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
        now = time.time()
        if self._last_pub:
            inst = 1.0 / max(now - self._last_pub, 1e-3)
            self.proc_fps = inst if not self.proc_fps else 0.9 * self.proc_fps + 0.1 * inst
        self._last_pub = now
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
        alerts_by_table: dict[str, list] = {}
        for al in engine.active_alerts.values():
            alerts_by_table.setdefault(al.table_id, []).append(al.type)
        tables = []
        for z in sorted(self.zones.get(), key=lambda z: z["id"]):
            tb = engine.tables.get(z["id"])
            occupied = tb is not None and tb.occupied_since is not None
            tables.append({
                "id": z["id"],
                "status": tb.status if tb else "LIBERA",
                "people_count": tb.people_count if tb else 0,
                "occupied_since": self._clock(tb.occupied_since) if occupied else None,
                "duration": (t - tb.occupied_since) if occupied else 0.0,
                "visits": tb.visit_count if occupied else 0,
                "first_visit_after": (tb.first_visit_t - tb.occupied_since) if occupied and tb.first_visit_t is not None else None,
                "served_after": (tb.served_t - tb.occupied_since) if occupied and tb.served_t is not None else None,
                "free_for": (t - tb.free_since) if tb and not occupied and tb.free_since is not None else 0.0,
                "alerts": alerts_by_table.get(z["id"], []),
            })
        events = []
        for e in engine.log.events:
            events.append({
                "type": e["type"], "table_id": e["table_id"], "people_count": e["people_count"],
                "time": self._clock(e["t"]), "duration": e.get("duration"), "after": e.get("after"),
                "alert": e.get("alert"), "message": e.get("message"),
            })
        return {
            "status": self.status, "error": self.error, "run_id": self.run_id, "source": self.source,
            "live": self.live, "connected": self.connected,
            "fps": round(self.proc_fps, 1), "target_fps": config.PROCESS_FPS,
            "history": self._history(),
            "clock": self._clock(t), "video_seconds": t, "progress": self.progress,
            "people_visible": self.people_tracks,
            "tables": tables, "stats": engine.stats(t), "events": events[::-1],
            "alerts": [{"key": k, "type": a.type, "table_id": a.table_id, "message": a.message}
                       for k, a in engine.active_alerts.items()],
        }

    # ---------- historial y exportación ----------
    def _history(self, max_points: int = 300) -> list[dict]:
        hist = list(self.engine.history)
        step = max(1, len(hist) // max_points)
        return [{"time": self._clock(t), "occupied": occ, "total": tot} for t, occ, tot in hist[::step]]

    def export_events_csv(self) -> str:
        labels = {"TABLE_OCCUPIED": "Mesa ocupada", "TABLE_FREED": "Mesa libre",
                  "TABLE_STAFF_VISIT": "Visita de personal (estimada)", "TABLE_SERVED": "Comida/bebida servida (estimado)",
                  "ALERT": "Aviso"}
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["hora", "mesa", "evento", "personas", "duracion_s", "detalle"])
        for e in self.engine.log.events:
            detail = e.get("message") or ""
            if e["type"] == "TABLE_SERVED":
                detail = f'{e["after"]:.0f} s tras sentarse'
            dur = e.get("duration")
            w.writerow([self._clock(e["t"]), e["table_id"], labels.get(e["type"], e["type"]), e["people_count"],
                        "" if dur is None else f"{dur:.0f}", detail])
        return out.getvalue()

    def export_sessions_csv(self) -> str:
        out = io.StringIO()
        w = csv.writer(out, delimiter=";")
        w.writerow(["mesa", "ocupada", "libre", "duracion_s", "visitas_personal", "servicio_tras_s", "estado"])
        for s_ in self.engine.log.sessions:
            w.writerow([s_["table_id"], self._clock(s_["start"]), self._clock(s_["end"]), f'{s_["duration"]:.0f}',
                        s_["visits"], "" if s_["service_delay"] is None else f'{s_["service_delay"]:.0f}', "cerrada"])
        for tid, tb in sorted(self.engine.tables.items()):
            if tb.occupied_since is not None:
                w.writerow([tid, self._clock(tb.occupied_since), "", f"{self.video_t - tb.occupied_since:.0f}",
                            tb.visit_count, "" if tb.served_t is None else f"{tb.served_t - tb.occupied_since:.0f}", "en curso"])
        return out.getvalue()
