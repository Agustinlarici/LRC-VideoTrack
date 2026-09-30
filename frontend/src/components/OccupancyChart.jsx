// Mesas ocupadas a lo largo del tiempo (gráfico de escalones, SVG sin dependencias).
export default function OccupancyChart({ history }) {
  if (!history || history.length < 2) return <p className="muted">El gráfico aparece cuando hay unos segundos de datos.</p>;

  const W = 640, H = 150, L = 28, R = 8, T = 8, B = 22;
  const total = Math.max(...history.map((h) => h.total), 1);
  const x = (i) => L + (i / (history.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - v / total) * (H - T - B);

  let line = `M ${x(0)} ${y(history[0].occupied)}`;
  history.forEach((h, i) => {
    if (i > 0) line += ` H ${x(i)} V ${y(h.occupied)}`;
  });
  const area = `${line} V ${y(0)} H ${x(0)} Z`;
  const ticks = Array.from({ length: total + 1 }, (_, i) => i);
  const last = history[history.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Mesas ocupadas a lo largo del tiempo">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid-line" />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" className="axis">{v}</text>
        </g>
      ))}
      <path d={area} className="area" />
      <path d={line} className="line" />
      <text x={L} y={H - 6} className="axis">{history[0].time}</text>
      <text x={W - R} y={H - 6} textAnchor="end" className="axis">{last.time}</text>
    </svg>
  );
}
