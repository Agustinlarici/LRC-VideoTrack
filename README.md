# Restaurant Vision (MVP local)

Sube un vídeo de una sala de restaurante, dibuja las mesas y el sistema detecta personas (YOLO), les hace tracking (ByteTrack), decide si cada mesa está `LIBERA` u `OCCUPATA`, registra los eventos y lo muestra en un dashboard web.

```
VIDEO → OpenCV → YOLO → ByteTrack → personas → zonas de mesas → motor de estados (debounce) → FastAPI → React
```

## Estructura

```
restaurant-vision/
├── requirements.txt
├── install.bat / start.bat  # instalación y arranque con doble clic (Windows)
├── README.md
├── backend/
│   ├── main.py              # app FastAPI (uvicorn backend.main:app)
│   ├── config.py            # modelo, umbrales de debounce, rutas (variables RV_*)
│   ├── vision/              # Computer Vision (no sabe nada de mesas)
│   │   ├── video_source.py  #   OpenCV: MP4 hoy, rtsp:// mañana (mismo código)
│   │   ├── detector.py      #   YOLO + ByteTrack, sólo clase person
│   │   └── annotator.py     #   dibuja cajas, IDs, mesas y estados
│   ├── services/            # Lógica de negocio (no sabe nada de YOLO)
│   │   ├── zones.py         #   mesas: guardado JSON + punto-en-polígono
│   │   ├── table_state.py   #   estados, debounce, eventos, estadísticas
│   │   └── pipeline.py      #   hilo que une todo
│   ├── api/routes.py        # endpoints REST + stream MJPEG
│   └── data/                # zones.json, source.json y vídeos subidos (local, ignorado por git)
├── scripts/setup_demo.py    # descarga el vídeo de demo y crea mesas de ejemplo
├── frontend/                # React + Vite, CSS simple
│   └── src/components/      # Dashboard, Setup, ZoneEditor
└── tests/test_table_state.py
```

## Instalación (Windows)

Requisitos: **Python 3.10–3.12** y **Node.js 18+** (con npm).

```bat
git clone <url-del-repo> restaurant-vision
cd restaurant-vision
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

**Atajo con doble clic:** `install.bat` hace todo lo anterior (venv, pip, npm) y `start.bat` arranca backend y frontend y abre el navegador.

La primera vez que se procesa un vídeo, Ultralytics descarga solo el modelo `yolov8n.pt` (~6 MB), así que hace falta internet ese día.

## Ejecución

Dos terminales, ambas en la carpeta del proyecto.

**Terminal 1 – backend**
```bat
.venv\Scripts\activate
uvicorn backend.main:app --port 8000
```

**Terminal 2 – frontend**
```bat
cd frontend
npm run dev
```

Abre http://localhost:5173

## Demo rápida (vídeo de prueba + mesas ya definidas)
Con el venv activo, en la carpeta del proyecto:
```bat
python scripts\setup_demo.py
```
Descarga un vídeo de restaurante de Mixkit (licencia gratuita, ~5 MB, 15 s, cámara elevada fija en la que se van llenando las mesas), lo deja como fuente y crea las mesas T01–T04. Después arranca backend y frontend, ve a *Dashboard* → **Iniciar procesamiento**. **Reinicia el backend** si ya estaba corriendo al ejecutar el script.

## Uso

1. **Cargar un vídeo**: pestaña *Configuración* → “Elegir archivo” (se copia a `backend/data/videos/`) o pega la ruta de un MP4 (`C:\videos\restaurant.mp4`) y pulsa “Usar esta fuente”.
2. **Crear las mesas**: en la misma pestaña aparece un frame del vídeo. Haz clic para marcar las esquinas de una mesa, escribe el nombre (`T01`, `T02`…) y pulsa **Cerrar mesa**. Se guarda automáticamente; con la × del chip la borras.
3. **Procesar**: pestaña *Dashboard* → indica la “hora de inicio del vídeo” (p. ej. `20:00`, para que los eventos salgan con hora real) → **Iniciar procesamiento**. El vídeo se procesa a velocidad real.
4. **Ver resultados**: mesas con estado y tiempo ocupadas, contadores (ocupadas, libres, % ocupación, tiempo medio), vídeo anotado y lista de eventos.

### Cómo comprobar que el tracking funciona
- En el vídeo procesado cada persona lleva una caja amarilla con `ID n`. El ID debe mantenerse mientras la persona se mueve.
- Un punto amarillo marca el centro de la caja: si está dentro del polígono, esa persona cuenta para la mesa.
- Cada mesa muestra `T01 OCCUPATA (2)`: estado y personas dentro. El polígono se pinta rojo (ocupada) o verde (libre).
- Prueba del debounce: una persona que cruza por delante de una mesa unos segundos **no** debe generar evento.
- Si faltan personas o los IDs cambian constantemente, prueba un modelo mayor: `set RV_YOLO_MODEL=yolov8s.pt` antes de arrancar el backend.

## Reglas de negocio
- Una persona pertenece a una mesa si el **centro de su bounding box** está dentro del polígono.
- El debounce usa una **ventana deslizante**, así un frame en que YOLO pierde a la persona no reinicia la cuenta:
  - `LIBERA → OCCUPATA`: en los últimos **2 s** (`RV_OCCUPY_SECONDS`) hubo gente en ≥80% de los frames.
  - `OCCUPATA → LIBERA`: en los últimos **3 s** (`RV_FREE_SECONDS`) hubo gente en ≤10% de los frames.
  - Estos valores están pensados para el vídeo de demo de 15 s. **Para un restaurante real sube los valores** (p. ej. `set RV_OCCUPY_SECONDS=30` y `set RV_FREE_SECONDS=120`).
- Eventos `TABLE_OCCUPIED` / `TABLE_FREED` con `table_id`, hora y `people_count`. La hora es la del momento en que *empezó* el cambio (no la de la confirmación). `TABLE_FREED` incluye la duración.
- Todos los tiempos usan el **reloj del vídeo** (frame/fps) sumado a la hora de inicio; no dependen de lo rápido que procese el PC.
- “Tiempo medio” = media de ocupaciones ya cerradas (si aún no hay ninguna, de las que están en curso).

## Pasar a RTSP más adelante
Todo entra por `backend/vision/video_source.py`. En *Configuración* puedes pegar `rtsp://...` como fuente y funciona con el mismo código (en directo el reloj es el tiempo real transcurrido). No hace falta tocar detección, lógica ni dashboard.

## Variables de entorno útiles
| Variable | Por defecto | Qué hace |
|---|---|---|
| `RV_YOLO_MODEL` | `yolov8n.pt` | Modelo YOLO (`yolov8s.pt` = más preciso, más lento) |
| `RV_YOLO_CONF` | `0.35` | Umbral de confianza |
| `RV_OCCUPY_SECONDS` / `RV_FREE_SECONDS` | `2` / `3` | Debounce (segundos de vídeo) |
| `RV_PROCESS_FPS` | `10` | Frames por segundo que pasan por YOLO; el resto se salta (el reloj sigue siendo exacto). Bájalo si tu PC va lento |
| `RV_YOLO_IMGSZ` | `640` | Tamaño de inferencia |

En CMD: `set RV_YOLO_MODEL=yolov8s.pt`. En PowerShell: `$env:RV_YOLO_MODEL="yolov8s.pt"`.

## GPU (opcional)
`pip install -r requirements.txt` instala PyTorch para CPU en Windows, suficiente para el MVP. Con tarjeta NVIDIA puedes instalar la build CUDA de PyTorch (https://pytorch.org/get-started/locally/) y Ultralytics la usará automáticamente.

## Tests
```bat
python tests\test_table_state.py
```

## Privacidad
No se guardan frames ni vídeo procesado: el vídeo anotado sólo existe en memoria y se envía al navegador. Sólo se guardan las coordenadas de las mesas y, si subes un archivo, la copia del MP4 en `backend/data/videos/`.
