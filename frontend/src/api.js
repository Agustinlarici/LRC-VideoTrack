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
