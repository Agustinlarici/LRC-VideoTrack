import { useCallback, useEffect, useState } from "react";
import { api, alertLabel, exportUrl, formatDuration, eventText, timeOf, hourOf } from "../api.js";

const dur = (v) => (v == null ? "—" : formatDuration(v));

function Kpi({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

// Mesas ocupadas de media por hora (barras) + nº de grupos que llegaron
function HourChart({ data }) {
  if (!data || data.length === 0) return <p className="muted">Sin datos.</p>;
  const W = 640, H = 170, L = 30, R = 8, T = 18, B = 24;
  const max = Math.max(...data.map((d) => d.avg_occupied), 1);
  const bw = Math.min(56, (W - L - R) / data.length - 8);
  const x = (i) => L + ((i + 0.5) / data.length) * (W - L - R);
  const y = (v) => T + (1 - v / max) * (H - T - B);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Ocupación por hora">
      <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} className="grid-line" />
      {data.map((d, i) => (
        <g key={d.hour}>
          <rect x={x(i) - bw / 2} y={y(d.avg_occupied)} width={bw} height={y(0) - y(d.avg_occupied)} className="bar" />
          <text x={x(i)} y={y(d.avg_occupied) - 4} textAnchor="middle" className="axis">{d.started} gr.</text>
          <text x={x(i)} y={H - 6} textAnchor="middle" className="axis">{hourOf(d.hour)}</text>
        </g>
      ))}
      <text x={L - 6} y={y(max) + 4} textAnchor="end" className="axis">{max}</text>
      <text x={L - 6} y={y(0) + 4} textAnchor="end" className="axis">0</text>
    </svg>
  );
}

// Personas y objetos en la mesa a lo largo de una visita
function SamplesChart({ samples }) {
  if (!samples || samples.length < 2) return <p className="muted small">Pocas muestras para dibujar el gráfico.</p>;
  const W = 640, H = 130, L = 26, R = 8, T = 8, B = 20;
  const max = Math.max(...samples.map((s) => Math.max(s.people, s.items)), 1);
  const x = (i) => L + (i / (samples.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - v / max) * (H - T - B);
  const path = (key) => samples.map((s, i) => (i === 0 ? `M ${x(0)} ${y(s[key])}` : `H ${x(i)} V ${y(s[key])}`)).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Personas y objetos en la mesa">
      <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} className="grid-line" />
      <path d={path("people")} className="line" />
      <path d={path("items")} className="line line2" />
      <text x={L} y={H - 4} className="axis">{timeOf(samples[0].ts)}</text>
      <text x={W - R} y={H - 4} textAnchor="end" className="axis">{timeOf(samples[samples.length - 1].ts)}</text>
      <text x={L - 4} y={y(max) + 4} textAnchor="end" className="axis">{max}</text>
      <text x={W - R} y={T + 8} textAnchor="end" className="axis"><tspan className="lg1">● personas </tspan><tspan className="lg2">● objetos</tspan></text>
    </svg>
  );
}

function SessionDetail({ id, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.historySession(id).then(setD).catch(() => setD(false));
  }, [id]);
  if (d === false) return <div className="banner error">No se pudo cargar la visita.</div>;
  if (!d) return <p className="muted">Cargando…</p>;
  const s = d.session;
  return (
    <section className="card detail">
      <div className="card-head">
        <h2>{s.table_id} · {timeOf(s.start)} → {s.end ? timeOf(s.end) : s.status === "open" ? "en curso" : "sin salida"}</h2>
        <button onClick={onClose}>Cerrar</button>
      </div>
      <p className="muted">
        {dur(s.duration)} · grupo {s.party_initial}{s.party_peak !== s.party_initial ? ` → máx. ${s.party_peak}` : ""} personas (aprox.) ·
        {" "}{s.visits.length} visitas de personal (est.)
        {s.first_visit_after != null && ` · 1ª a los ${dur(s.first_visit_after)}`}
        {s.served_after != null && ` · servicio a los ${dur(s.served_after)}`}
        {s.cleared_after != null && ` · recogida a los ${dur(s.cleared_after)}`}
        {s.cleaned_after != null && ` · limpiada ${dur(s.cleaned_after)} tras salir`}
        {s.turnaround != null && ` · ${dur(s.turnaround)} libre desde el grupo anterior`}
      </p>
      <SamplesChart samples={d.samples} />
      <ul className="events">
        {d.timeline.map((e, i) => (
          <li key={i} className={e.type === "ALERT" ? "is-alert" : ""}>
            <span className="mono">{timeOf(e.ts)}</span> — {eventText(e)}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function History() {
  const [days, setDays] = useState(null);
  const [date, setDate] = useState("");
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");
  const [summary, setSummary] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [selected, setSelected] = useState(null);

  const loadDays = useCallback(async () => {
    const r = await api.historyDays();
    setDays(r.days);
    setDate((cur) => (r.days.some((d) => d.day === cur) ? cur : r.days[0]?.day || ""));
  }, []);

  useEffect(() => {
    loadDays();
  }, [loadDays]);

  const params = { date, run_id: runId };
  const load = useCallback(async () => {
    if (!date) return;
    const [r, sm, se] = await Promise.all([api.historyRuns(date), api.historySummary(params), api.historySessions(params)]);
    setRuns(r.runs);
    setSummary(sm);
    setSessions(se.sessions);
  }, [date, runId]); // eslint-disable-line

  useEffect(() => {
    load();
    const id = setInterval(load, 5000); // se actualiza solo mientras hay una ejecución en marcha
    return () => clearInterval(id);
  }, [load]);

  if (days === null) return <p className="muted">Cargando…</p>;
  if (days.length === 0) return <div className="banner">Todavía no hay datos. Procesa un vídeo o una cámara desde el Dashboard y aquí quedará el registro completo.</div>;

  const removeRun = async () => {
    if (runId && window.confirm(`¿Borrar la ejecución #${runId} del historial?`)) {
      await api.deleteRun(runId);
      setRunId("");
      setSelected(null);
      loadDays();
    }
  };
  const removeAll = async () => {
    if (window.confirm("¿Borrar TODO el historial? No se puede deshacer.")) {
      await api.deleteHistory();
      setSelected(null);
      loadDays();
    }
  };

  const sm = summary;
  return (
    <>
      <section className="card controls">
        <label>
          Día
          <select value={date} onChange={(e) => { setDate(e.target.value); setRunId(""); setSelected(null); }}>
            {days.map((d) => <option key={d.day} value={d.day}>{d.day} ({d.events} eventos)</option>)}
          </select>
        </label>
        <label>
          Ejecución
          <select value={runId} onChange={(e) => { setRunId(e.target.value); setSelected(null); }}>
            <option value="">Todas</option>
            {runs.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.source.split(/[\\/]/).pop().slice(0, 28)}</option>)}
          </select>
        </label>
        <span className="export">
          <a href={exportUrl("sessions", params)} download>Visitas (CSV)</a>
          <a href={exportUrl("events", params)} download>Todos los eventos (CSV)</a>
        </span>
        <span className="export">
          {runId && <button className="link" onClick={removeRun}>Borrar esta ejecución</button>}
          <button className="link" onClick={removeAll}>Borrar todo</button>
        </span>
      </section>

      {sm && (
        <>
          <section className="stats stats-4">
            <Kpi label="Grupos atendidos" value={sm.sessions} sub={`${sm.covers} comensales (aprox.) · grupo medio ${sm.avg_party ? sm.avg_party.toFixed(1) : "—"}`} />
            <Kpi label="Estancia media" value={dur(sm.avg_stay)} sub={sm.median_stay != null ? `mediana ${dur(sm.median_stay)}` : ""} />
            <Kpi label="Ocupación media" value={sm.occupancy_pct != null ? `${sm.occupancy_pct}%` : "—"} sub={`${sm.tables} mesas`} />
            <Kpi label="Rotación (mesa libre entre grupos)" value={dur(sm.avg_turnaround)} />
            <Kpi label="Primera atención (est.)" value={dur(sm.avg_first_visit)} sub={sm.unattended_pct != null ? `${sm.unattended_pct}% de grupos sin visita` : ""} />
            <Kpi label="Tiempo hasta servicio (est.)" value={dur(sm.avg_service)} sub={sm.served_pct != null ? `servicio detectado en ${sm.served_pct}%` : ""} />
            <Kpi label="Cambios de grupo" value={sm.party_changes} sub="llegan / se van comensales" />
            <Kpi label="Avisos" value={Object.values(sm.alerts).reduce((a, b) => a + b, 0)}
                 sub={Object.entries(sm.alerts).map(([k, v]) => `${v} ${alertLabel(k).toLowerCase()}`).join(" · ")} />
          </section>

          <div className="grid2">
            <section className="card">
              <h2>Mesas ocupadas por hora</h2>
              <HourChart data={sm.by_hour} />
            </section>
            <section className="card">
              <h2>Por mesa</h2>
              <table className="tbl">
                <thead><tr><th>Mesa</th><th>Grupos</th><th>Estancia</th><th>Ocup.</th><th>1ª visita</th><th>Servicio</th></tr></thead>
                <tbody>
                  {sm.per_table.map((t) => (
                    <tr key={t.table_id}>
                      <td><b>{t.table_id}</b></td><td>{t.sessions}</td><td>{dur(t.avg_stay)}</td>
                      <td>{t.occupancy_pct != null ? `${t.occupancy_pct}%` : "—"}</td><td>{dur(t.avg_first_visit)}</td><td>{dur(t.avg_service)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </>
      )}

      {selected && <SessionDetail id={selected} onClose={() => setSelected(null)} />}

      <section className="card">
        <h2>Visitas de mesa</h2>
        <table className="tbl clickable">
          <thead>
            <tr><th>Mesa</th><th>Llegada</th><th>Salida</th><th>Duración</th><th>Grupo</th><th>Visitas</th><th>1ª visita</th><th>Servicio</th><th>Avisos</th><th></th></tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} onClick={() => setSelected(s.id)} className={selected === s.id ? "sel" : ""}>
                <td><b>{s.table_id}</b></td><td>{timeOf(s.start)}</td><td>{s.end ? timeOf(s.end) : "—"}</td>
                <td>{dur(s.duration)}</td>
                <td>{s.party_initial}{s.party_peak !== s.party_initial ? `→${s.party_peak}` : ""}</td>
                <td>{s.visits.length}</td><td>{dur(s.first_visit_after)}</td><td>{dur(s.served_after)}</td>
                <td>{s.alerts.length ? <span className="badge">{s.alerts.length}</span> : ""}</td>
                <td>{s.status === "open" ? <span className="pill running">en curso</span> : s.status === "cut" ? <span className="pill" title="El vídeo o la cámara terminó con la mesa todavía ocupada">sin salida</span> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Pulsa una fila para ver la línea de tiempo completa de esa visita. Los datos “est.” y “aprox.” son estimaciones (ver README).</p>
      </section>
    </>
  );
}
