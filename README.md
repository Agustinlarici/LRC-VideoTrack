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
│   │   ├── service_monitor.py #  visitas de personal y comida servida (heurísticas)
│   │   ├── alerts.py        #   reglas de avisos
│   │   ├── settings.py      #   umbrales editables (JSON)
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

## Avisos y servicio a la mesa (estimados)
Además de libre/ocupada, el sistema estima el servicio y genera avisos. **Son heurísticas sobre YOLO genérico, no reconocimiento de camareros ni de platos**; en el dashboard llevan la etiqueta *estimado*.

| Qué | Cómo se deduce |
|---|---|
| **Visita de personal** | Una persona que *entra andando desde fuera* de la mesa, permanece entre 3 s y 60 s y se va, con la mesa ocupada. Un comensal que reaparece con otro ID *dentro* de la mesa no cuenta. |
| **Comida/bebida servida** | YOLO detecta objetos sobre la mesa (botella, copa, taza, bol, cubiertos, comida) cada 0,5 s. Si el número sube ≥1 sobre el que había al sentarse y se sostiene 3 s, se marca servicio. |
| **Tiempo hasta servicio** | Desde que se ocupa la mesa hasta esa detección. |

**Avisos** (un aviso por ocupación; umbrales editables en el dashboard, 0 = desactivado):

| Aviso | Salta cuando… | Por defecto (real) |
|---|---|---|
| Sin atender | ocupada sin visita de personal | 5 min |
| Sin servicio | ocupada sin comida/bebida detectada | 15 min |
| Ocupación larga | ocupada más de… | 90 min |
| Libre sin ocupar | libre más de… | 30 min |

Salen en el panel superior del dashboard, con un pitido si está activado, y en la lista de eventos. Si pones una URL en **Webhook**, cada evento (ocupada, libre, visita, servicio, aviso) se envía como POST JSON: sirve para conectar Slack, n8n, Make o un bot de Telegram.
Botones de preset: **Restaurante real** y **Demo (vídeo corto)**, que baja todo a segundos para poder ver los avisos en un clip de 15 s.

Limitaciones a tener en cuenta: no distingue camarero de cliente (una persona que atraviesa la zona de una mesa ≥3 s puede contar como visita); desde una cámara elevada los objetos pequeños se pierden y pueden dar falsos servicios o no detectarlos; con mesas adyacentes, los comensales en el borde pueden contarse en la mesa vecina. Para precisión comercial haría falta afinar/entrenar un modelo con imágenes de la sala.

## Conectar una cámara
En *Configuración* → campo de fuente, y pulsa **Probar conexión** antes de **Usar esta fuente**:

- **Cámara IP (RTSP):** `rtsp://usuario:clave@192.168.1.50:554/stream1`. La URL exacta depende de la marca (Hikvision, Dahua, Tapo, Reolink…); usa el flujo *secundario* (sub-stream) de 720p si la CPU va justa. Se fuerza RTSP sobre TCP.
- **Webcam USB:** `0` (o `1`, `2`…).
- En directo el reloj es la hora real, no hay “hora de inicio”, se descartan frames si YOLO va lento (para no acumular retraso) y si la cámara se cae se **reconecta sola** (el dashboard muestra “RECONECTANDO CÁMARA…”).
- Tras cambiar de vídeo a cámara, redibuja las mesas sobre su imagen.

## Reglas de negocio
- Una persona pertenece a una mesa si el **centro de su bounding box** está dentro del polígono.
- El debounce usa una **ventana deslizante**, así un frame en que YOLO pierde a la persona no reinicia la cuenta:
  - `LIBERA → OCCUPATA`: en los últimos *N* s hubo gente en ≥80% de los frames.
  - `OCCUPATA → LIBERA`: en los últimos *M* s hubo gente en ≤10% de los frames.
  - *N* y *M* se editan en el dashboard (Avisos y umbrales): **30 s / 120 s** en un restaurante real (preset “real”), 2 s / 3 s para vídeos cortos (preset “demo”, que aplica `setup_demo.py`). Se aplican al pulsar “Iniciar”.
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
| `RV_ITEM_MODEL` / `RV_ITEM_IMGSZ` | mismo modelo / `1280` | Modelo y resolución para detectar objetos sobre la mesa |
| `RV_VISIT_MIN` / `RV_VISIT_MAX` | `3` / `60` | Permanencia (s) que cuenta como visita de personal |
| `RV_DATA_DIR` | `backend/data` | Dónde se guardan mesas, ajustes y vídeos |
| `RV_PROCESS_FPS` | `10` | Frames por segundo que pasan por YOLO; el resto se salta (el reloj sigue siendo exacto). Bájalo si tu PC va lento |
| `RV_YOLO_IMGSZ` | `640` | Tamaño de inferencia |

En CMD: `set RV_YOLO_MODEL=yolov8s.pt`. En PowerShell: `$env:RV_YOLO_MODEL="yolov8s.pt"`.

## GPU (opcional)
`pip install -r requirements.txt` instala PyTorch para CPU en Windows, suficiente para el MVP. Con tarjeta NVIDIA puedes instalar la build CUDA de PyTorch (https://pytorch.org/get-started/locally/) y Ultralytics la usará automáticamente.

## Tests
```bat
python tests\test_table_state.py
python tests\test_service_monitor.py
python tests\test_pipeline_fake.py
```
`test_pipeline_fake.py` ejecuta el pipeline completo (ocupación, visita, servicio, avisos, webhook) con detectores simulados, sin YOLO.

## Privacidad
No se guardan frames ni vídeo procesado: el vídeo anotado sólo existe en memoria y se envía al navegador. Sólo se guardan las coordenadas de las mesas y, si subes un archivo, la copia del MP4 en `backend/data/videos/`.
