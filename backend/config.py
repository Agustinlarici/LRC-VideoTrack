"""Configuración central. Todo se puede sobreescribir con variables de entorno RV_*."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
ZONES_FILE = DATA_DIR / "zones.json"
SOURCE_FILE = DATA_DIR / "source.json"

DATA_DIR.mkdir(exist_ok=True)
VIDEOS_DIR.mkdir(exist_ok=True)

# --- Visión ---
YOLO_MODEL = os.getenv("RV_YOLO_MODEL", "yolov8n.pt")  # se descarga solo la primera vez
YOLO_CONF = float(os.getenv("RV_YOLO_CONF", "0.35"))
YOLO_IMGSZ = int(os.getenv("RV_YOLO_IMGSZ", "640"))
TRACKER = os.getenv("RV_TRACKER", "bytetrack.yaml")  # tracker incluido en ultralytics
PERSON_CLASS_ID = 0  # COCO: 0 = person

# --- Lógica de mesas (segundos de VÍDEO, no de reloj real) ---
OCCUPY_SECONDS = float(os.getenv("RV_OCCUPY_SECONDS", "5"))  # LIBERA -> OCCUPATA
FREE_SECONDS = float(os.getenv("RV_FREE_SECONDS", "10"))     # OCCUPATA -> LIBERA

# --- Stream hacia el dashboard ---
STREAM_MAX_WIDTH = int(os.getenv("RV_STREAM_MAX_WIDTH", "960"))
STREAM_JPEG_QUALITY = int(os.getenv("RV_STREAM_JPEG_QUALITY", "70"))
