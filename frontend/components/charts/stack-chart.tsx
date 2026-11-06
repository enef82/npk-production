/**
 * Столбчатая диаграмма с накоплением — простой SVG без библиотек (по `stackChart`
 * прототипа). Числа здесь только для геометрии и подписей, денежных расчётов нет.
 */
export type StackSeries = { name: string; color: string; values: number[] };
/** Линия поверх столбцов (мощность, план) — пунктир, как `opt.line` прототипа. */
export type StackLine = { name: string; values: number[]; color?: string };

export function StackChart({
  categories,
  series,
  height = 220,
  format = (v: number) => Math.round(v).toLocaleString("ru-RU"),
  showTotals = true,
  highlight,
  onCategoryClick,
  width = 780,
  line,
  topLabels,
}: {
  categories: string[];
  series: StackSeries[];
  height?: number;
  format?: (v: number) => string;
  showTotals?: boolean;
  highlight?: number;
  onCategoryClick?: (index: number) => void;
  /** Ширина viewBox: для узких панелей меньше, чтобы подписи не мельчили. */
  width?: number;
  line?: StackLine;
  /** Подпись над столбцом вместо суммы (например, доля от плана). */
  topLabels?: string[];
}) {
  const W = width;
  const ml = 58;
  const mr = 12;
  const mt = 18;
  const mb = 28;
  const iw = W - ml - mr;
  const ih = height - mt - mb;
  const n = Math.max(categories.length, 1);
  const step = iw / n;
  const bw = Math.min(54, step * 0.62);
  const totals = categories.map((_, i) => series.reduce((s, se) => s + Math.max(0, se.values[i] ?? 0), 0));
  const max = Math.max(1, ...totals, ...(line?.values ?? [])) * 1.12;
  const y = (v: number) => mt + ih - (v / max) * ih;
  const ticks = [0, 1, 2, 3, 4].map((k) => ((max / 1.12) * k) / 4);
  const labelEvery = Math.ceil(categories.length / Math.max(4, Math.floor(W / 50)));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${height}`} className="block h-auto w-full" role="img">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={ml} x2={W - mr} y1={y(v)} y2={y(v)} stroke="var(--border)" />
            <text x={ml - 6} y={y(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--muted-foreground)">
              {format(v)}
            </text>
          </g>
        ))}
        {categories.map((cat, i) => {
          const x = ml + step * i + (step - bw) / 2;
          let acc = 0;
          return (
            <g
              key={`${cat}-${i}`}
              onClick={onCategoryClick ? () => onCategoryClick(i) : undefined}
              style={onCategoryClick ? { cursor: "pointer" } : undefined}
            >
              {series.map((se) => {
                const v = Math.max(0, se.values[i] ?? 0);
                if (v <= 0) return null;
                const y1 = y(acc + v);
                const h = y(acc) - y1;
                acc += v;
                return (
                  <rect key={se.name} x={x} y={y1} width={bw} height={Math.max(0, h)} fill={se.color} rx={2}>
                    <title>{`${cat} · ${se.name}: ${format(v)}`}</title>
                  </rect>
                );
              })}
              {(topLabels ? Boolean(topLabels[i]) : showTotals && acc > 0) && (
                <text x={x + bw / 2} y={y(acc) - 5} textAnchor="middle" fontSize="10.5" fontWeight={600} fill="currentColor">
                  {topLabels ? topLabels[i] : format(acc)}
                </text>
              )}
              {i % labelEvery === 0 && (
                <text
                  x={ml + step * i + step / 2}
                  y={height - 9}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight={highlight === i ? 700 : 400}
                  fill={highlight === i ? "var(--primary)" : "var(--muted-foreground)"}
                >
                  {cat}
                </text>
              )}
            </g>
          );
        })}
        {line && (
          <polyline
            points={line.values.map((v, i) => `${ml + step * i + step / 2},${y(v)}`).join(" ")}
            fill="none"
            stroke={line.color ?? "#c53030"}
            strokeWidth={2}
            strokeDasharray="5 3"
          >
            <title>{line.name}</title>
          </polyline>
        )}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((se) => (
          <span key={se.name} className="inline-flex items-center gap-1.5">
            <i className="inline-block size-2.5 rounded-sm" style={{ background: se.color }} />
            {se.name}
          </span>
        ))}
        {line && (
          <span className="inline-flex items-center gap-1.5">
            <i className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: line.color ?? "#c53030" }} />
            {line.name}
          </span>
        )}
      </div>
    </div>
  );
}
