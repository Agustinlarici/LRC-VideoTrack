import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .. import config
from ..services.pipeline import Pipeline
from ..services.settings import PRESETS, Settings
from ..services.zones import ZoneStore
from ..vision.video_source import grab_first_frame, is_live

router = APIRouter(prefix="/api")

zones = ZoneStore()
settings = Settings()
pipeline = Pipeline(zones, settings)


def _get_source() -> str:
    if config.SOURCE_FILE.exists():
        return json.loads(config.SOURCE_FILE.read_text(encoding="utf-8")).get("source", "")
    return ""


def _set_source(source: str):
    config.SOURCE_FILE.write_text(json.dumps({"source": source}), encoding="utf-8")


# ---------- fuente de vídeo ----------
class SourceBody(BaseModel):
    source: str  # ruta local a un MP4, o rtsp://...


@router.get("/source")
def get_source():
    return {"source": _get_source()}


@router.post("/source")
def set_source(body: SourceBody):
    source = body.source.strip().strip('"')
    if not is_live(source) and not Path(source).is_file():
        raise HTTPException(400, f"No existe el archivo: {source}")
    _set_source(source)
    return {"source": source}


@router.post("/source/test")
def test_source(body: SourceBody):
    """Comprueba que una cámara/URL abre y entrega frames (sin guardar nada)."""
    source = body.source.strip().strip('"')
    if not is_live(source) and not Path(source).is_file():
        return {"ok": False, "error": f"No existe el archivo: {source}"}
    image = grab_first_frame(source)
    if image is None:
        return {"ok": False, "error": "No se pudo leer ningún frame. Revisa la URL, usuario/contraseña y que la cámara sea accesible desde este PC."}
    h, w = image.shape[:2]
    return {"ok": True, "width": w, "height": h, "live": is_live(source)}


@router.post("/source/upload")
def upload_video(file: UploadFile = File(...)):
    name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "video.mp4")
    dest = config.VIDEOS_DIR / f"{uuid.uuid4().hex[:8]}_{name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    _set_source(str(dest))
    return {"source": str(dest)}


@router.get("/frame")
def first_frame():
    """Primer frame de la fuente (sin anotar) para dibujar las mesas."""
    source = _get_source()
    if not source:
        raise HTTPException(404, "Primero carga un vídeo")
    image = grab_first_frame(source)
    if image is None:
        raise HTTPException(500, "No se pudo leer el vídeo")
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(buf.tobytes(), media_type="image/jpeg")


# ---------- mesas ----------
class ZoneBody(BaseModel):
    id: str
    points: list[list[float]]  # normalizados 0..1


class ZonesBody(BaseModel):
    zones: list[ZoneBody]


@router.get("/zones")
def get_zones():
    return {"zones": zones.get()}


@router.put("/zones")
def put_zones(body: ZonesBody):
    return {"zones": zones.save([z.model_dump() for z in body.zones])}


# ---------- procesamiento ----------
class StartBody(BaseModel):
    start_time: str | None = None  # hora "del vídeo" al empezar, ej. "20:00" (vacío = ahora)
    realtime: bool = True


@router.post("/pipeline/start")
def start(body: StartBody):
    source = _get_source()
    if not source:
        raise HTTPException(400, "Primero carga un vídeo")
    if not zones.get():
        raise HTTPException(400, "Define al menos una mesa antes de iniciar")
    try:
        pipeline.start(source, body.start_time, body.realtime)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.post("/pipeline/stop")
def stop():
    pipeline.stop()
    return {"ok": True}


class SettingsBody(BaseModel):
    occupy_seconds: float | None = None
    free_seconds: float | None = None
    unattended_seconds: float | None = None
    service_seconds: float | None = None
    long_stay_seconds: float | None = None
    free_idle_seconds: float | None = None
    sound: bool | None = None
    webhook_url: str | None = None
    preset: str | None = None  # "real" | "demo"


@router.get("/settings")
def get_settings():
    return settings.get()


@router.put("/settings")
def put_settings(body: SettingsBody):
    changes = body.model_dump(exclude={"preset"})
    if body.preset:
        if body.preset not in PRESETS:
            raise HTTPException(400, f"Preset desconocido: {body.preset}")
        changes = {**PRESETS[body.preset], **{k: v for k, v in changes.items() if v is not None}}
    return settings.update(changes)


@router.get("/state")
def state():
    return pipeline.snapshot()


# ---------- vídeo procesado ----------
BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"


@router.get("/snapshot")
def snapshot():
    if pipeline.latest_jpeg is None:
        raise HTTPException(404, "Aún no hay frames procesados")
    return Response(pipeline.latest_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/stream")
async def stream():
    """MJPEG del vídeo anotado. Termina solo cuando el procesamiento acaba."""
    async def gen():
        last = -1
        while True:
            if pipeline.frame_id != last and pipeline.latest_jpeg:
                last = pipeline.frame_id
                yield BOUNDARY + pipeline.latest_jpeg + b"\r\n"
            elif pipeline.status not in ("running", "loading"):
                return
            await asyncio.sleep(0.03)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
