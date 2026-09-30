async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

const qs = (params = {}) => {
  const q = Object.entries(params).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  return q.length ? `?${q.join("&")}` : "";
};
export const exportUrl = (kind, params) => `/api/history/export/${kind}.csv${qs(params)}`;

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  state: () => request("/state"),
  getSource: () => request("/source"),
  setSource: (source) => request("/source", json("POST", { source })),
  uploadVideo: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/source/upload", { method: "POST", body: form });
  },
  testSource: (source) => request("/source/test", json("POST", { source })),
  getSettings: () => request("/settings"),
  saveSettings: (settings) => request("/settings", json("PUT", settings)),
  historyDays: () => request("/history/days"),
  historyRuns: (date) => request(`/history/runs${qs({ date })}`),
  historySummary: (p) => request(`/history/summary${qs(p)}`),
  historySessions: (p) => request(`/history/sessions${qs(p)}`),
  historySession: (id) => request(`/history/session${qs({ id })}`),
  deleteRun: (id) => request(`/history/run/${id}`, { method: "DELETE" }),
  deleteHistory: () => request("/history", { method: "DELETE" }),
  getZones: () => request("/zones"),
  saveZones: (zones) => request("/zones", json("PUT", { zones })),
  start: (opts) => request("/pipeline/start", json("POST", opts)),
  stop: () => request("/pipeline/stop", { method: "POST" }),
};

const TYPE_LABEL = {
  UNATTENDED: "Sin atender",
  SERVICE_SLOW: "Sin servicio",
  LONG_STAY: "Ocupación larga",
  FREE_IDLE: "Libre sin ocupar",
};
export const alertLabel = (type) => TYPE_LABEL[type] || type;

export function formatDuration(seconds) {
  const s = Math.floor(seconds || 0);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} min`;
}

export const timeOf = (iso) => (iso ? new Date(iso).toLocaleTimeString("es", { hour12: false }) : "—");
export const hourOf = (iso) => new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", hour12: false });

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Texto de un evento del historial (mismos tipos que el feed en vivo)
export function eventText(e) {
  switch (e.type) {
    case "TABLE_OCCUPIED": return `Se sienta un grupo de ${plural(e.people_count, "persona", "personas")}`;
    case "TABLE_FREED": return `Mesa libre${e.duration != null ? ` · estuvo ocupada ${formatDuration(e.duration)}` : ""}`;
    case "TABLE_STAFF_VISIT": return `Visita de personal (est.)${e.duration != null ? ` · ${formatDuration(e.duration)}` : ""}`;
    case "TABLE_SERVED": return `Comida/bebida servida (est.)${e.after != null ? ` · ${formatDuration(e.after)} tras sentarse` : ""}`;
    case "TABLE_CLEARED": return "Mesa recogida (est.)";
    case "TABLE_CLEANED": return "Mesa limpiada/preparada (est.)";
    case "PARTY_SIZE_CHANGED": return `El grupo pasa de ${e.prev} a ${plural(e.people_count, "persona", "personas")} (aprox.)`;
    case "ITEMS_CHANGED": {
      const names = e.names ? Object.entries(e.names).map(([k, v]) => `${v}× ${k}`).join(", ") : "";
      return `Objetos sobre la mesa: ${e.prev_items} → ${e.items}${names ? ` (${names})` : ""}`;
    }
    case "ALERT": return `⚠ ${alertLabel(e.alert)}: ${e.message}`;
    default: return e.type;
  }
}
