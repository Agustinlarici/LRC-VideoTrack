import { useEffect, useState } from "react";
import { api } from "../api.js";
import ZoneEditor from "./ZoneEditor.jsx";

export default function Setup() {
  const [source, setSource] = useState("");
  const [path, setPath] = useState("");
  const [version, setVersion] = useState(0); // fuerza a recargar el frame
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getSource().then((s) => {
      setSource(s.source);
      setPath(s.source);
    });
  }, []);

  const [test, setTest] = useState(null);

  const testConnection = async () => {
    setTest({ pending: true });
    try {
      setTest(await api.testSource(path));
    } catch (e) {
      setTest({ ok: false, error: e.message });
    }
  };

  const apply = async (promise) => {
    setMsg("");
    try {
      const res = await promise;
      setSource(res.source);
      setPath(res.source);
      setVersion((v) => v + 1);
    } catch (e) {
      setMsg(e.message);
    }
  };

  return (
    <>
      <section className="card">
        <h2>1. Vídeo</h2>
        <div className="row">
          <input type="file" accept="video/*" onChange={(e) => e.target.files[0] && apply(api.uploadVideo(e.target.files[0]))} />
        </div>
        <div className="row">
          <input
            className="grow"
            placeholder={'Ruta local (C:\\videos\\restaurant.mp4), rtsp://... o 0 para webcam'}
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <button onClick={testConnection}>Probar conexión</button>
          <button className="primary" onClick={() => apply(api.setSource(path))}>Usar esta fuente</button>
        </div>
        {test && (
          <div className={`banner ${test.ok === false ? "error" : ""}`}>
            {test.pending ? "Probando…" : test.ok ? `Conexión correcta: ${test.width}×${test.height}${test.live ? " (directo)" : ""}` : test.error}
          </div>
        )}
        <p className="muted small">
          Cámara IP: <code>rtsp://usuario:clave@192.168.1.50:554/stream1</code> · Webcam USB: <code>0</code> (o <code>1</code>…)
        </p>
        {msg && <div className="banner error">{msg}</div>}
        <p className="muted">Fuente actual: {source || "ninguna"}</p>
      </section>
      <ZoneEditor hasSource={!!source} version={version} />
    </>
  );
}
