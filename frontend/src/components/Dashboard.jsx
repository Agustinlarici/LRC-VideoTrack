import { useState } from "react";
import { api, formatDuration } from "../api.js";

const TYPE_TEXT = { TABLE_OCCUPIED: "ocupada", TABLE_FREED: "libre" };

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function Dashboard({ state, goSetup }) {
  const [startTime, setStartTime] = useState("20:00");
  const [error, setError] = useState("");

  if (!state) return <p className="muted">Cargando…</p>;

  const running = state.status === "running" || state.status === "loading";
  const hasVideo = state.status === "running" || state.status === "finished";

  const start = async () => {
    setError("");
    try {
      await api.start({ start_time: startTime, realtime: true });
    } catch (e) {
      setError(e.message);
    }
  };

  const { stats } = state;
  return (
    <>
      <section className="card controls">
        {running ? (
          <button className="danger" onClick={() => api.stop()}>■ Detener</button>
        ) : (
          <button className="primary" onClick={start}>▶ Iniciar procesamiento</button>
        )}
        <label>
          Hora inicio del vídeo
          <input value={startTime} onChange={(e) => setStartTime(e.target.value)} size={8} disabled={running} />
        </label>
        <span className={`pill ${state.status}`}>{state.status}</span>
        <span className="muted">
          Reloj del vídeo: <b>{state.clock}</b>
          {state.progress > 0 && ` · ${Math.round(state.progress * 100)}%`} · personas visibles: {state.people_visible}
        </span>
        <button className="link" onClick={goSetup}>Cambiar vídeo / mesas</button>
      </section>
      {(error || state.error) && <div className="banner error">{error || state.error}</div>}
      {state.source === "" && !error && <div className="banner">Carga un vídeo y define las mesas en “Configuración”.</div>}

      <section className="stats">
        <Stat label="Ocupadas" value={stats.occupied} />
        <Stat label="Libres" value={stats.free} />
        <Stat label="Ocupación" value={`${stats.occupancy_pct}%`} />
        <Stat label="Tiempo medio" value={stats.avg_duration ? formatDuration(stats.avg_duration) : "—"} />
      </section>

      <div className="grid">
        <section className="card">
          <h2>Mesas</h2>
          {state.tables.length === 0 && <p className="muted">No hay mesas definidas.</p>}
          {state.tables.map((t) => (
            <div key={t.id} className={`table-row ${t.status === "OCCUPATA" ? "occ" : "free"}`}>
              <span className="table-id">{t.id}</span>
              <span className="table-status">{t.status}</span>
              <span className="table-time">
                {t.status === "OCCUPATA" ? `${formatDuration(t.duration)} · ${t.people_count} pers.` : ""}
              </span>
            </div>
          ))}
        </section>

        <section className="card video">
          <h2>Vídeo procesado</h2>
          {hasVideo ? (
            <img
              key={state.run_id}
              src={state.status === "running" ? `/api/stream?run=${state.run_id}` : `/api/snapshot?run=${state.run_id}`}
              alt="vídeo procesado"
            />
          ) : (
            <p className="muted">{state.status === "loading" ? "Cargando modelo YOLO…" : "Inicia el procesamiento para ver el vídeo."}</p>
          )}
        </section>
      </div>

      <section className="card">
        <h2>Eventos</h2>
        {state.events.length === 0 && <p className="muted">Sin eventos todavía.</p>}
        <ul className="events">
          {state.events.map((e, i) => (
            <li key={i}>
              <span className="mono">{e.time}</span> — <b>{e.table_id}</b> {TYPE_TEXT[e.type]} — {e.people_count}{" "}
              {e.people_count === 1 ? "persona" : "personas"}
              {e.duration != null && <span className="muted"> · duración {formatDuration(e.duration)}</span>}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
