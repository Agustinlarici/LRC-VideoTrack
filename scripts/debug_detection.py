"""Herramienta de calibración: compara los perfiles de detección (fast / balanced / accurate) sobre
frames de TU vídeo o cámara y guarda una imagen con las cajas para revisarla a ojo.

    python scripts\\debug_detection.py C:\\videos\\restaurant.mp4
    python scripts\\debug_detection.py rtsp://usuario:clave@192.168.1.50/stream1

Si el perfil `balanced` no encuentra a todos los comensales de tu sala, prueba `accurate`
(set RV_PROFILE=accurate). Escribe `detection_debug.jpg` en la carpeta actual (sólo para depuración).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from backend import config  # noqa: E402
from backend.vision.video_source import grab_first_frame, is_live  # noqa: E402

N_FRAMES = 4


def sample_frames(source: str) -> list:
    if is_live(source):
        first = grab_first_frame(source)
        return [first] if first is not None else []
    cap = cv2.VideoCapture(source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    frames = []
    for i in np.linspace(total * 0.1, total * 0.9, N_FRAMES).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if ok:
            frames.append(f)
    return frames


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    frames = sample_frames(sys.argv[1])
    if not frames:
        sys.exit("No se pudo leer el vídeo/cámara.")
    from ultralytics import YOLO

    rows = []
    for name, (weights, imgsz, max_imgsz) in config._PROFILES.items():
        model = YOLO(weights)
        tiles, counts, t0 = [], [], time.time()
        for f in frames:
            h, w = f.shape[:2]
            size = min(max(-(-max(w, h) // 32) * 32, imgsz), max(max_imgsz, imgsz))
            res = model.predict(f, classes=[0], conf=config.YOLO_CONF, iou=config.YOLO_IOU, imgsz=size, verbose=False)[0]
            g = f.copy()
            for (x1, y1, x2, y2), c in zip(res.boxes.xyxy.tolist(), res.boxes.conf.tolist()):
                cv2.rectangle(g, (int(x1), int(y1)), (int(x2), int(y2)), (0, 220, 255), 2)
                cv2.putText(g, f"{c:.2f}", (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
            counts.append(len(res.boxes))
            tiles.append(cv2.resize(g, (480, int(480 * h / w))))
        ms = (time.time() - t0) / len(frames) * 1000
        print(f"{name:9s} ({weights}, imgsz {imgsz}-{max_imgsz}): personas por frame {counts} · {ms:.0f} ms/frame")
        row = np.hstack(tiles)
        cv2.putText(row, name, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        rows.append(row)
    cv2.imwrite("detection_debug.jpg", np.vstack(rows))
    print("Guardado detection_debug.jpg: cuenta a ojo cuántas personas hay y elige el perfil más barato que las encuentre a todas.")


if __name__ == "__main__":
    main()
