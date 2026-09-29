import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const nextName = (zones) => {
  let n = zones.length + 1;
  while (zones.some((z) => z.id === `T${String(n).padStart(2, "0")}`)) n++;
  return `T${String(n).padStart(2, "0")}`;
};

export default function ZoneEditor({ hasSource, version }) {
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const [zones, setZones] = useState([]); // [{id, points:[[x,y]...]}] normalizados 0..1
  const [current, setCurrent] = useState([]); // polígono en construcción
  const [name, setName] = useState("T01");
  const [imgReady, setImgReady] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getZones().then((r) => {
      setZones(r.zones);
      setName(nextName(r.zones));
    });
  }, []);

  useEffect(() => setImgReady(false), [version]);

  // Redibuja el canvas cada vez que cambia algo
  useEffect(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas || !imgReady) return;
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;
    const lw = Math.max(2, W / 400);
    ctx.clearRect(0, 0, W, H);
    ctx.font = `bold ${Math.round(W / 45)}px sans-serif`;

    zones.forEach((z) => {
      ctx.beginPath();
      z.points.forEach(([x, y], i) => (i ? ctx.lineTo(x * W, y * H) : ctx.moveTo(x * W, y * H)));
      ctx.closePath();
      ctx.fillStyle = "rgba(60,180,90,0.30)";
      ctx.fill();
      ctx.strokeStyle = "#3cb45a";
      ctx.lineWidth = lw;
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 3;
      ctx.strokeText(z.id, z.points[0][0] * W + 6, z.points[0][1] * H - 6);
      ctx.fillText(z.id, z.points[0][0] * W + 6, z.points[0][1] * H - 6);
    });

    if (current.length) {
      ctx.beginPath();
      current.forEach(([x, y], i) => (i ? ctx.lineTo(x * W, y * H) : ctx.moveTo(x * W, y * H)));
      ctx.strokeStyle = "#ffd400";
      ctx.lineWidth = lw;
      ctx.stroke();
      current.forEach(([x, y]) => {
        ctx.beginPath();
        ctx.arc(x * W, y * H, lw * 2.2, 0, Math.PI * 2);
        ctx.fillStyle = "#ffd400";
        ctx.fill();
      });
    }
  }, [zones, current, imgReady]);

  const persist = async (next) => {
    setZones(next);
    try {
      const saved = await api.saveZones(next);
      setZones(saved.zones);
      setMsg("Guardado ✓");
    } catch (e) {
      setMsg(e.message);
    }
  };

  const onCanvasClick = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    setCurrent([...current, [(e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height]]);
  };

  const closePolygon = () => {
    const id = name.trim().toUpperCase();
    if (current.length < 3) return setMsg("Un polígono necesita al menos 3 puntos");
    if (!id) return setMsg("Pon un nombre a la mesa");
    if (zones.some((z) => z.id === id)) return setMsg(`Ya existe la mesa ${id}`);
    const next = [...zones, { id, points: current }];
    setCurrent([]);
    setName(nextName(next));
    persist(next);
  };

  return (
    <section className="card">
      <h2>2. Mesas</h2>
      {!hasSource ? (
        <p className="muted">Primero carga un vídeo.</p>
      ) : (
        <>
          <p className="muted">
            Haz clic sobre la imagen para marcar las esquinas de la mesa, escribe el nombre y pulsa “Cerrar mesa”.
            Las mesas se guardan automáticamente.
          </p>
          <div className="row">
            <input value={name} onChange={(e) => setName(e.target.value)} size={6} />
            <button className="primary" onClick={closePolygon} disabled={current.length < 3}>Cerrar mesa</button>
            <button onClick={() => setCurrent(current.slice(0, -1))} disabled={!current.length}>Deshacer punto</button>
            <button onClick={() => setCurrent([])} disabled={!current.length}>Cancelar</button>
            <span className="muted">{msg}</span>
          </div>
          <div className="editor">
            <img
              ref={imgRef}
              src={`/api/frame?v=${version}`}
              alt="frame del vídeo"
              onLoad={() => setImgReady(true)}
              onError={() => setMsg("No se pudo leer un frame del vídeo")}
            />
            <canvas ref={canvasRef} onClick={onCanvasClick} />
          </div>
          <div className="zone-list">
            {zones.map((z) => (
              <span key={z.id} className="chip">
                {z.id}
                <button onClick={() => persist(zones.filter((o) => o.id !== z.id))} title="Borrar">×</button>
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
