"""Dibuja personas, IDs y mesas sobre el frame."""
import cv2
import numpy as np

from .detector import Item, Person

GREEN = (80, 200, 80)
RED = (60, 60, 230)
WHITE = (255, 255, 255)
YELLOW = (0, 220, 255)
ITEM = (255, 170, 60)


def _label(img, text, org, color, scale=0.55):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    x, y = int(org[0]), int(org[1])
    cv2.rectangle(img, (x, y - h - 6), (x + w + 6, y + 2), color, -1)
    cv2.putText(img, text, (x + 3, y - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, WHITE, 1, cv2.LINE_AA)


def annotate(image: np.ndarray, people: list[Person], items: list[Item], tables: list[dict]) -> np.ndarray:
    """`tables`: [{id, polygon(np.int32 Nx2), status, people_count}]"""
    out = image.copy()

    overlay = out.copy()
    for t in tables:
        color = RED if t["status"] == "OCCUPATA" else GREEN
        cv2.fillPoly(overlay, [t["polygon"]], color)
    out = cv2.addWeighted(overlay, 0.25, out, 0.75, 0)

    for t in tables:
        color = RED if t["status"] == "OCCUPATA" else GREEN
        cv2.polylines(out, [t["polygon"]], True, color, 2, cv2.LINE_AA)
        x, y = t["polygon"].min(axis=0)
        _label(out, f'{t["id"]} {t["status"]} ({t["people_count"]})', (x, max(y, 20)), color)

    for it in items:
        cv2.rectangle(out, (int(it.x1), int(it.y1)), (int(it.x2), int(it.y2)), ITEM, 1)
        cv2.putText(out, it.name, (int(it.x1), max(int(it.y1) - 3, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, ITEM, 1, cv2.LINE_AA)

    for p in people:
        cv2.rectangle(out, (int(p.x1), int(p.y1)), (int(p.x2), int(p.y2)), YELLOW, 2)
        cx, cy = p.center
        cv2.circle(out, (int(cx), int(cy)), 4, YELLOW, -1)
        _label(out, f"ID {p.track_id}", (p.x1, p.y1), (0, 140, 170), scale=0.5)
    return out
