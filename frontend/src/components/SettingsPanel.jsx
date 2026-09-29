import { useEffect, useState } from "react";
import { api, formatDuration } from "../api.js";

const FIELDS = [
  ["unattended_seconds", "Aviso: mesa sin atender", "Ocupada sin visita del personal durante…"],
  ["service_seconds", "Aviso: sin comida/bebida", "Ocupada sin que se sirva nada durante…"],
  ["long_stay_seconds", "Aviso: ocupación larga", "Ocupada más de…"],
  ["free_idle_seconds", "Aviso: mesa libre", "Libre sin ocuparse durante…"],
  ["occupy_seconds", "Confirmar ocupada tras", "Debounce LIBERA → OCCUPATA"],
  ["free_seconds", "Confirmar libre tras", "Debounce OCCUPATA → LIBERA"],
];

export default function SettingsPanel() {
  const [s, setS] = useState(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getSettings().then(setS);
  }, []);

  if (!s) return null;

  const save = async (changes) => {
    try {
      setS(await api.saveSettings(changes));
      setMsg("Guardado ✓");
    } catch (e) {
      setMsg(e.message);
    }
  };

  return (
    <section className="card">
      <h2>Avisos y umbrales</h2>
      <div className="row">
        <button onClick={() => save({ preset: "real" })}>Preset restaurante real</button>
        <button onClick={() => save({ preset: "demo" })}>Preset demo (vídeo corto)</button>
        <span className="muted">{msg}</span>
      </div>
      <div className="settings-grid">
        {FIELDS.map(([key, label, hint]) => (
          <label key={key} title={hint}>
            <span>{label}</span>
            <input
              type="number"
              min="0"
              value={s[key]}
              onChange={(e) => setS({ ...s, [key]: e.target.value })}
              onBlur={() => save({ [key]: Number(s[key]) })}
            />
            <small className="muted">segundos {s[key] >= 60 ? `(${formatDuration(s[key])})` : ""} · 0 = desactivado</small>
          </label>
        ))}
      </div>
      <div className="row">
        <label className="inline">
          <input type="checkbox" checked={s.sound} onChange={(e) => save({ sound: e.target.checked })} /> Sonido en avisos nuevos
        </label>
        <input
          className="grow"
          placeholder="Webhook opcional (Slack, n8n, Make…): se envía un POST JSON por cada evento"
          value={s.webhook_url}
          onChange={(e) => setS({ ...s, webhook_url: e.target.value })}
          onBlur={() => save({ webhook_url: s.webhook_url })}
        />
      </div>
      <p className="muted">
        Los umbrales de avisos se aplican en directo. La confirmación de ocupada/libre se aplica al pulsar “Iniciar”.
      </p>
    </section>
  );
}
