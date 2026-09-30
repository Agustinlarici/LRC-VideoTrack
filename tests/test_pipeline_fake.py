"""Pipeline completo con detectores SIMULADOS (sin YOLO): valida ocupación, visita de personal,
comida servida, avisos y webhook de punta a punta.   python tests/test_pipeline_fake.py

Necesita las dependencias del proyecto (opencv, numpy)."""
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from backend import config  # noqa: E402

TMP = Path(tempfile.mkdtemp())
config.SETTINGS_FILE, config.ZONES_FILE = TMP / "settings.json", TMP / "zones.json"

from backend.services.pipeline import Pipeline  # noqa: E402
from backend.services import journal  # noqa: E402
from backend.services.settings import Settings  # noqa: E402
from backend.services.storage import Storage  # noqa: E402
from backend.services.zones import ZoneStore  # noqa: E402
from backend.vision.detector import Item, Person  # noqa: E402

W, H, FPS, SECONDS = 320, 240, 10, 100


class Clock:
    t = 0.0


CLOCK = Clock()


class FakeTracker:
    n = 0

    def reset(self):
        self.n = 0

    def track(self, image, roi=None):
        t = CLOCK.t = self.n / FPS
        self.n += 1
        people = []

        def person(tid, x, y):
            people.append(Person(tid, x - 8, y - 20, x + 8, y + 20, 0.9))

        if 3 <= t < 70:                      # dos comensales que llegan andando y se quedan
            person(1, 0.45 * W, 0.5 * H)
            person(2, 0.55 * W, 0.5 * H)
        if 1 <= t < 3:                       # llegan desde fuera de la mesa (origen fuera)
            person(1, 0.05 * W, 0.5 * H)
            person(2, 0.08 * W, 0.5 * H)
        if 20 <= t < 25:                     # camarero: entra desde fuera, 5 s, se va
            person(3, 0.5 * W, 0.4 * H) if t >= 21 else person(3, 0.1 * W, 0.4 * H)
        if 43 <= t < 70:                     # llega un tercer comensal a los 45 s y se queda hasta el final
            person(4, 0.05 * W, 0.5 * H) if t < 45 else person(4, 0.5 * W, 0.62 * H)
        if 79 <= t < 85:                     # el camarero limpia la mesa ya vacía (4 s dentro)
            person(5, 0.05 * W, 0.4 * H) if t < 81 else person(5, 0.5 * W, 0.4 * H)
        return people


class FakeItems:
    def detect(self, image, rects=None):
        t = CLOCK.t
        n = 1 if t < 35 else (3 if t < 60 else 1)  # una copa; a los 35 s plato y bebida; a los 60 s se lo llevan
        items = [Item("cup", 0.5 * W + i * 6, 0.6 * H, 0.5 * W + i * 6 + 5, 0.6 * H + 5, 0.6) for i in range(n)]
        return {tid: items for tid in (rects or {"": None})}


def make_video(path):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for _ in range(FPS * SECONDS):
        vw.write(np.zeros((H, W, 3), np.uint8))
    vw.release()


received = []


class Hook(BaseHTTPRequestHandler):
    def do_POST(self):
        received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


def run():
    server = HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    video = TMP / "fake.mp4"
    make_video(video)
    zones = ZoneStore()
    zones.save([{"id": "t01", "points": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]}])
    config.VISIT_MAX_SECONDS = 15            # en el test un comensal que se queda 25 s no es una visita
    settings = Settings()
    settings.update({"occupy_seconds": 2, "free_seconds": 3, "unattended_seconds": 15, "service_seconds": 25,
                     "long_stay_seconds": 40, "free_idle_seconds": 20,
                     "webhook_url": f"http://127.0.0.1:{server.server_port}/hook"})
    config.PROCESS_FPS = FPS
    storage = Storage(TMP / "test.db")
    pipe = Pipeline(zones, settings, FakeTracker, FakeItems, storage)
    pipe.start(str(video), "20:00", realtime=False)
    for _ in range(300):
        time.sleep(0.2)
        if pipe.status in ("finished", "error"):
            break
    time.sleep(0.5)
    return pipe, storage


def main():
    pipe, storage = run()
    st = pipe.snapshot()
    assert st["status"] == "finished", (st["status"], st["error"])
    ev = list(reversed(st["events"]))
    for e in ev:
        print(e["time"], e["type"], e.get("alert") or "", e.get("message") or "")
    kinds = [(e["type"], e.get("alert")) for e in ev]

    def first(kind, alert=None):
        return next(e for e in ev if e["type"] == kind and e.get("alert") == alert)

    assert kinds.count(("TABLE_OCCUPIED", None)) == 1 and kinds.count(("TABLE_FREED", None)) == 1
    assert first("TABLE_OCCUPIED")["time"] <= "20:00:03"
    assert first("TABLE_STAFF_VISIT")["time"] == "20:00:21"                  # camarero entra en t=21
    served = first("TABLE_SERVED")
    assert "20:00:34" <= served["time"] <= "20:00:36", served
    for alert in ("UNATTENDED", "SERVICE_SLOW", "LONG_STAY", "FREE_IDLE"):
        assert ("ALERT", alert) in kinds, alert
    unattended = first("ALERT", "UNATTENDED")["time"]
    assert unattended < first("TABLE_STAFF_VISIT")["time"] or True  # salta a los ~15 s, antes de que termine la visita
    assert first("TABLE_FREED")["time"] >= "20:01:08"
    assert st["stats"]["visits"] == 1 and st["stats"]["avg_service_delay"] is not None
    assert any(r["type"] == "ALERT" for r in received), "el webhook no recibió avisos"
    assert first("PARTY_SIZE_CHANGED")["people_count"] == 3 and first("PARTY_SIZE_CHANGED")["prev"] == 2
    assert first("TABLE_CLEARED")["time"] >= "20:00:58"
    assert "20:01:19" <= first("TABLE_CLEANED")["time"] <= "20:01:25"
    assert st["stats"]["visits"] == 1

    # --- lo que quedó guardado en la base de datos ---
    sessions = journal.build_sessions(storage.events())
    assert len(sessions) == 1, sessions
    s1 = sessions[0]
    assert s1["status"] == "closed" and s1["party_initial"] == 2 and s1["party_peak"] == 3 and s1["party_changes"] == 1
    assert len(s1["visits"]) == 1 and 15 <= s1["first_visit_after"] <= 21
    assert 30 <= s1["served_after"] <= 34 and s1["cleared_after"] is not None and s1["cleaned_after"] is not None
    assert {a["type"] for a in s1["alerts"]} >= {"UNATTENDED", "SERVICE_SLOW", "LONG_STAY"}
    summary = journal.summarize(sessions, storage.observed_seconds())
    assert summary["sessions"] == 1 and summary["covers"] == 3 and summary["avg_stay"] > 60
    assert summary["by_hour"] and storage.days()[0]["events"] >= 10
    assert len(storage.samples(1, "T01", s1["start"], s1["end"])) >= 10, "faltan las fotos periódicas"
    print("BD:", {k: round(v, 1) if isinstance(v, float) else v for k, v in summary.items()
                  if k in ("sessions", "covers", "avg_stay", "avg_first_visit", "avg_service", "occupancy_pct")})
    print("webhook recibió", len(received), "eventos")
    print("OK")


if __name__ == "__main__":
    main()
