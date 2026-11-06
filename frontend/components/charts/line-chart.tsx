/**
 * Линейный график получасового профиля (48 точек) — простой SVG по `lineChart`
 * прототипа: сетка, заливка под линией, пик, необязательная базовая линия и
 * подсветка интервалов (рабочая смена).
 */
const W = 780;
const H = 200;

export function LineChart({
  values,
  unit,
  shade,
  base,
  xLabel = (i: number) => `${String(Math.floor(i / 2)).padStart(2, "0")}:00`,
  labelStep = 4,
}: {
  values: number[];
  unit: string;
  shade?: boolean[];
  base?: number;
  xLabel?: (i: number) => string;
  labelStep?: number;
}) {
  const ml = 48;
  const mr = 10;
  const mt = 14;
  const mb = 26;
  const iw = W - ml - mr;
  const ih = H - mt - mb;
  const n = values.length;
  if (n < 2) return <p className="text-sm text-muted-foreground">Нет данных.</p>;
  const max = Math.max(1, ...values) * 1.15;
  const x = (i: number) => ml + (iw * i) / (n - 1);
  const y = (v: number) => mt + ih - (v / max) * ih;
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join("");
  const peak = values.indexOf(Math.max(...values));
  const fmt = (v: number) => Math.round(v).toLocaleString("ru-RU");
  const cell = iw / (n - 1);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Профиль суток">
      {shade?.map((s, i) =>
        s ? <rect key={i} x={x(i) - cell / 2} y={mt} width={cell} height={ih} fill="#eef4ff" /> : null,
      )}
      {[0, 1, 2, 3, 4].map((k) => {
        const v = ((max / 1.15) * k) / 4;
        return (
          <g key={k}>
            <line x1={ml} x2={W - mr} y1={y(v)} y2={y(v)} stroke="var(--border)" />
            <text x={ml - 6} y={y(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--muted-foreground)">
              {fmt(v)}
            </text>
          </g>
        );
      })}
      {values.map((_, i) =>
        i % labelStep === 0 ? (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10.5" fill="var(--muted-foreground)">
            {xLabel(i)}
          </text>
        ) : null,
      )}
      <path d={`${path}L${x(n - 1)} ${y(0)}L${x(0)} ${y(0)}Z`} fill="#2f5bd3" opacity={0.08} />
      <path d={path} fill="none" stroke="#2f5bd3" strokeWidth={2} />
      <circle cx={x(peak)} cy={y(values[peak])} r={4} fill="#c53030" />
      <text
        x={x(peak)}
        y={y(values[peak]) - 8}
        textAnchor="middle"
        fontSize="11"
        fontWeight={600}
        fill="#c53030"
      >
        {fmt(values[peak])} {unit}
      </text>
      {base !== undefined && (
        <g>
          <line x1={ml} x2={W - mr} y1={y(base)} y2={y(base)} stroke="#b7791f" strokeDasharray="5 3" />
          <text x={W - mr} y={y(base) - 4} textAnchor="end" fontSize="10.5" fill="#b7791f">
            базовая нагрузка {fmt(base)} {unit}
          </text>
        </g>
      )}
    </svg>
  );
}
