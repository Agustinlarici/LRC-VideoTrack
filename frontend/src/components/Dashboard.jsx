import { useEffect, useRef, useState } from "react";
import { api, formatDuration, alertLabel } from "../api.js";
import OccupancyChart from "./OccupancyChart.jsx";
import SettingsPanel from "./SettingsPanel.jsx";

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.15;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch {}
}

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

const plural = (n) => `${n} ${n === 1 ? "persona" : "personas"}`;

function EventLine({ e }) {
  const who = <b>{e.table_id}</b>;
  switch (e.type) {
    case "TABLE_OCCUPIED":
      return <>{who} ocupada — {plural(e.people_count)}</>;
    case "TABLE_FREED":
      return <>{who} libre — {plural(e.people_count)}<span className="muted"> · duración {formatDuration(e.duration)}</span></>;
    case "TABLE_STAFF_VISIT":
      return <>{who} visita de personal <span className="tag">estimado</span><span className="muted"> · {formatDuration(e.duration)}</span></>;
    case "TABLE_SERVED":
      return <>{who} comida/bebida servida <span className="tag">estimado</span><span className="muted"> · {formatDuration(e.after)} tras sentarse</span></>;
    case "ALERT":
      return <span className="alert-line">⚠ {alertLabel(e.alert)}: {e.message}</span>;
    default:
      return <>{who} {e.type}</>;
  }
}

function TableRow({ t }) {
  const occ = t.status === "OCCUPATA";
  return (
    <div className={`table-row ${occ ? "occ" : "free"} ${t.alerts.length ? "warn" : ""}`}>
      <div className="table-main">
        <span className="table-id">{t.id}</span>
        <span className="table-status">{t.status}</span>
        <span className="table-time">{occ ? `${formatDuration(t.duration)} · ${t.people_count} pers.` : t.free_for > 0 ? `libre ${formatDuration(t.free_for)}` : ""}</span>
      </div>
      {occ && (
        <div className="table-sub">
          <span>{t.visits ? `Atendida ${t.visits}× (1ª a los ${formatDuration(t.first_visit_after)})` : "Sin visita de personal"}</span>
          <span>{t.served_after != null ? `Servida a los ${formatDuration(t.served_after)}` : "Sin comida/bebida"}</span>
        </div>
      )}
      {t.alerts.length > 0 && (
        <div className="table-alerts">{t.alerts.map((a) => <span key={a} className="badge">{alertLabel(a)}</span>)}</div>
      )}
    </div>
  );
}

export default function Dashboard({ state, goSetup }) {
  const [startTime, setStartTime] = useState("20:00");
  const [error, setError] = useState("");
  const seenAlerts = useRef(null);
  const [sound, setSound] = useState(true);

  useEffect(() => {
    api.getSettings().then((s) => setSound(s.sound)).catch(() => {});
  }, []);

  // Sonido al aparecer un aviso nuevo (no en el primer estado cargado ni tras reiniciar)
  useEffect(() => {
    if (!state) return;
    const keys = new Set(state.alerts.map((a) => a.key));
    if (seenAlerts.current && state.status === "running" && sound) {
      if ([...keys].some((k) => !seenAlerts.current.has(k))) beep();
    }
    seenAlerts.current = keys;
  }, [state, sound]);

  if (!state) return <p className="muted">Cargando…</p>;

  const running = state.status === "running" || state.status === "loading";
  const hasVideo = state.status === "running" || state.status === "finished";
  const isLive = state.live || /^(rtsp|rtmp|https?):\/\//i.test(state.source) || /^\d+$/.test(state.source);

  const start = async () => {
    setError("");
    seenAlerts.current = null;
    try {
      await api.start({ start_time: isLive ? "" : startTime, realtime: true });
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
        {!isLive && (
          <label>
            Hora inicio del vídeo
            <input value={startTime} onChange={(e) => setStartTime(e.target.value)} size={8} disabled={running} />
          </label>
        )}
        <span className={`pill ${state.status}`}>{isLive && state.status === "running" ? "EN DIRECTO" : state.status}</span>
        {isLive && state.status === "running" && !state.connected && <span className="pill error">RECONECTANDO CÁMARA…</span>}
        {state.status === "running" && state.fps > 0 && (
          <span className={`pill ${!isLive && state.fps < state.target_fps * 0.7 ? "warn" : ""}`}
                title="Frames por segundo que analiza el PC">
            {state.fps} fps{!isLive && state.fps < state.target_fps * 0.7 ? " · PC lento" : ""}
          </span>
        )}
        <span className="muted">
          {isLive ? "Hora" : "Reloj del vídeo"}: <b>{state.clock}</b>
          {state.progress > 0 && ` · ${Math.round(state.progress * 100)}%`} · personas visibles: {state.people_visible}
        </span>
        <button className="link" onClick={goSetup}>Cambiar vídeo / mesas</button>
      </section>
      {(error || state.error) && <div className="banner error">{error || state.error}</div>}
      {state.source === "" && !error && <div className="banner">Carga un vídeo o conecta una cámara y define las mesas en “Configuración”.</div>}

      {state.alerts.length > 0 && (
        <section className="alerts">
          {state.alerts.map((a) => (
            <div key={a.key} className="alert-card">
              <b>⚠ {alertLabel(a.type)}</b> — {a.message}
            </div>
          ))}
        </section>
      )}

      <section className="stats">
        <Stat label="Ocupadas" value={stats.occupied} sub={`${stats.free} libres`} />
        <Stat label="Ocupación" value={`${stats.occupancy_pct}%`} />
        <Stat label="Tiempo medio de ocupación" value={stats.avg_duration ? formatDuration(stats.avg_duration) : "—"} />
        <Stat
          label="Tiempo hasta servicio (est.)"
          value={stats.avg_service_delay != null ? formatDuration(stats.avg_service_delay) : "—"}
          sub={`${stats.visits} visitas de personal (est.) · ${stats.active_alerts} avisos activos`}
        />
      </section>

      <div className="grid">
        <section className="card">
          <h2>Mesas</h2>
          {state.tables.length === 0 && <p className="muted">No hay mesas definidas.</p>}
          {state.tables.map((t) => <TableRow key={t.id} t={t} />)}
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
        <h2>Ocupación en el tiempo</h2>
        <OccupancyChart history={state.history} />
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Eventos y avisos</h2>
          <span className="export">
            <a href="/api/export/events.csv" download>Descargar eventos (CSV)</a>
            <a href="/api/export/sessions.csv" download>Descargar ocupaciones (CSV)</a>
          </span>
        </div>
        {state.events.length === 0 && <p className="muted">Sin eventos todavía.</p>}
        <ul className="events">
          {state.events.map((e, i) => (
            <li key={i} className={e.type === "ALERT" ? "is-alert" : ""}>
              <span className="mono">{e.time}</span> — <EventLine e={e} />
            </li>
          ))}
        </ul>
        <p className="muted small">
          “Estimado” = deducido por comportamiento / detección de objetos genérica (YOLO), no reconocimiento de camareros ni de platos.
        </p>
      </section>

      <SettingsPanel />
    </>
  );
}
