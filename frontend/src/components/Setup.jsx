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
            placeholder={'Ruta local (C:\\videos\\restaurant.mp4) o rtsp://...'}
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <button onClick={() => apply(api.setSource(path))}>Usar esta fuente</button>
        </div>
        {msg && <div className="banner error">{msg}</div>}
        <p className="muted">Fuente actual: {source || "ninguna"}</p>
      </section>
      <ZoneEditor hasSource={!!source} version={version} />
    </>
  );
}
