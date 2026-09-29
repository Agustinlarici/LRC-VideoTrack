"""Prepara la demo: descarga un vídeo de restaurante (Mixkit, licencia gratuita),
lo deja como fuente actual y crea 4 mesas de ejemplo.

    python scripts\\setup_demo.py
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import config  # noqa: E402

URL = "https://assets.mixkit.co/videos/4385/4385-720.mp4"  # "Customers in a minimalist style restaurant"
DEST = config.VIDEOS_DIR / "demo_restaurant.mp4"

# Coordenadas normalizadas (0..1) sobre ese vídeo
DEMO_ZONES = [  # cada zona cubre una mesa y sus asientos (mesa + banco + sillas)
    {"id": "T01", "points": [[0.49, 0.26], [0.75, 0.26], [0.75, 0.42], [0.49, 0.42]]},
    {"id": "T02", "points": [[0.49, 0.42], [0.75, 0.42], [0.75, 0.55], [0.49, 0.55]]},
    {"id": "T03", "points": [[0.49, 0.55], [0.75, 0.55], [0.75, 0.70], [0.49, 0.70]]},
    {"id": "T04", "points": [[0.49, 0.70], [0.75, 0.70], [0.75, 0.97], [0.49, 0.97]]},
]

if not DEST.exists():
    print("Descargando vídeo de demo...")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    DEST.write_bytes(urllib.request.urlopen(req, timeout=60).read())
config.SOURCE_FILE.write_text(json.dumps({"source": str(DEST)}), encoding="utf-8")
config.ZONES_FILE.write_text(json.dumps({"zones": DEMO_ZONES}, indent=2), encoding="utf-8")
print(f"Listo: {DEST}\nMesas: T01..T04. Arranca el backend y el frontend e inicia el procesamiento.")
