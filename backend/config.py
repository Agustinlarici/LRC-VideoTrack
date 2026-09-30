"""Configuración central. Todo se puede sobreescribir con variables de entorno RV_*."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("RV_DATA_DIR", BASE_DIR / "data"))
VIDEOS_DIR = DATA_DIR / "videos"
ZONES_FILE = DATA_DIR / "zones.json"
SOURCE_FILE = DATA_DIR / "source.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "restaurant.db"

DATA_DIR.mkdir(exist_ok=True)
VIDEOS_DIR.mkdir(exist_ok=True)

# --- Visión ---
# Perfil: fast = yolov8n (PC modesto) | balanced = yolov8s (por defecto) | accurate = yolov8s a mayor resolución
PROFILE = os.getenv("RV_PROFILE", "balanced").lower()
_PROFILES = {  # (modelo, imgsz base personas, imgsz máximo)
    "fast": ("yolov8n.pt", 640, 640),
    "balanced": ("yolov8s.pt", 640, 960),
    "accurate": ("yolov8s.pt", 960, 1280),
}
_model, _imgsz, _max_imgsz = _PROFILES.get(PROFILE, _PROFILES["balanced"])
YOLO_MODEL = os.getenv("RV_YOLO_MODEL", _model)  # se descarga solo la primera vez
YOLO_CONF = float(os.getenv("RV_YOLO_CONF", "0.35"))
TRACK_MIN_CONF = float(os.getenv("RV_TRACK_MIN_CONF", "0.1"))  # ByteTrack usa las de baja confianza para no perder IDs
YOLO_IOU = float(os.getenv("RV_YOLO_IOU", "0.6"))
YOLO_IMGSZ = int(os.getenv("RV_YOLO_IMGSZ", str(_imgsz)))
MAX_IMGSZ = int(os.getenv("RV_MAX_IMGSZ", str(_max_imgsz)))  # tope al ampliar la resolución en cámaras HD/4K
TRACKER = os.getenv("RV_TRACKER", str(BASE_DIR / "vision" / "bytetrack_restaurant.yaml"))
USE_ROI = os.getenv("RV_USE_ROI", "1") != "0"        # detectar sólo dentro de las mesas (+ margen)
ROI_MARGIN = float(os.getenv("RV_ROI_MARGIN", "0.25"))  # margen alrededor de las mesas, para ver llegar a la gente
PERSON_CLASS_ID = 0  # COCO: 0 = person
PROCESS_FPS = float(os.getenv("RV_PROCESS_FPS", "10"))  # frames/s que pasan por YOLO (el resto se salta)

# --- Lógica de mesas (segundos de VÍDEO, no de reloj real) ---
OCCUPY_SECONDS = float(os.getenv("RV_OCCUPY_SECONDS", "2"))  # LIBERA -> OCCUPATA
FREE_SECONDS = float(os.getenv("RV_FREE_SECONDS", "3"))     # OCCUPATA -> LIBERA

# --- Registro ---
SAMPLE_SECONDS = float(os.getenv("RV_SAMPLE_SECONDS", "5"))  # foto de cada mesa (estado, personas, objetos) cada N s de vídeo

# --- Stream hacia el dashboard ---
STREAM_MAX_WIDTH = int(os.getenv("RV_STREAM_MAX_WIDTH", "960"))
STREAM_JPEG_QUALITY = int(os.getenv("RV_STREAM_JPEG_QUALITY", "70"))

# --- Objetos sobre la mesa (comida / bebida), detectados con YOLO a baja frecuencia ---
# COCO: 39 botella, 40 copa, 41 taza, 42 tenedor, 43 cuchillo, 44 cuchara, 45 bol, 46-55 comida
ITEM_CLASS_IDS = [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]
ITEM_MODEL = os.getenv("RV_ITEM_MODEL", YOLO_MODEL)
ITEM_CONF = float(os.getenv("RV_ITEM_CONF", "0.25"))
ITEM_IMGSZ = int(os.getenv("RV_ITEM_IMGSZ", "640"))  # se aplica a cada recorte de mesa
ITEM_INTERVAL = float(os.getenv("RV_ITEM_INTERVAL", "1.0"))  # mínimo de segundos entre detecciones de objetos (se espacia solo si el PC va justo)
ITEM_MARGIN = 0.15  # margen del recorte de cada mesa

# --- Visitas de personal (estimadas por comportamiento) ---
# Visita = una persona que ENTRA andando desde fuera de la mesa, se queda entre VISIT_MIN y VISIT_MAX
# segundos y se va, mientras la mesa está ocupada.
VISIT_MIN_SECONDS = float(os.getenv("RV_VISIT_MIN", "3"))
VISIT_MAX_SECONDS = float(os.getenv("RV_VISIT_MAX", "60"))
VISIT_LEAVE_GRACE = 1.0  # segundos sin verla en la mesa para darla por salida
# Tras irse los clientes, el personal limpia/prepara la mesa: durante CLEAN_WINDOW segundos la ocupación
# exige CLEAN_FACTOR veces más presencia, para que un camarero limpiando no cuente como comensal.
CLEAN_WINDOW_SECONDS = float(os.getenv("RV_CLEAN_WINDOW", "600"))
CLEAN_FACTOR = float(os.getenv("RV_CLEAN_FACTOR", "3"))
SERVICE_CONFIRM_SECONDS = float(os.getenv("RV_SERVICE_CONFIRM", "3"))  # objetos nuevos sostenidos

# --- Avisos: valores por defecto de un restaurante real (segundos; 0 = desactivado) ---
DEFAULT_SETTINGS = {
    "occupy_seconds": OCCUPY_SECONDS,
    "free_seconds": FREE_SECONDS,
    "unattended_seconds": 300,      # mesa ocupada sin visita de personal
    "service_seconds": 900,         # mesa ocupada sin comida/bebida servida
    "long_stay_seconds": 5400,      # ocupación larga
    "free_idle_seconds": 1800,      # mesa libre sin volver a ocuparse
    "sound": True,
    "webhook_url": "",
}
