import type { QualityParetoOut, WeekQcOut } from "@/lib/api/endpoints";
import { formatDate } from "@/lib/format/ru";

const INTERMEDIATE = "#2f5bd3";
const FINAL = "#c53030";

/**
 * Брак по неделям: где выявлен (`stackChart` прототипа) — промежуточный контроль снизу,
 * финальный сверху, над столбцом доля брака от проверенного. Чистый SVG без библиотек.
 */
export function WeeklyDefectsChart({ weeks }: { weeks: WeekQcOut[] }) {
  const width = 780;
  const height = 240;
  const left = 40;
  const right = 12;
  const top = 22;
  const bottom = 30;
  const innerW = width - left - right;
  const innerH = height - top - bottom;
  const totals = weeks.map((w) => w.intermediate_defects + w.final_defects);
  const max = Math.max(1, ...totals) * 1.12;
  const step = innerW / Math.max(1, weeks.length);
  const barW = Math.min(44, step * 0.62);
  const y = (v: number) => top + innerH - (v / max) * innerH;
  const ticks = [0, 1, 2, 3, 4].map((k) => Math.round(((max / 1.12) * k) / 4));

  return (
    <figure className="flex flex-col gap-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Брак по неделям">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke="currentColor" strokeOpacity={0.1} />
            <text x={left - 6} y={y(t) + 4} textAnchor="end" fontSize={10.5} fill="currentColor" fillOpacity={0.6}>
              {t}
            </text>
          </g>
        ))}
        {weeks.map((w, i) => {
          const x = left + step * i + (step - barW) / 2;
          const yInter = y(w.intermediate_defects);
          const yTotal = y(w.intermediate_defects + w.final_defects);
          return (
            <g key={w.week_start}>
              <rect x={x} y={yInter} width={barW} height={top + innerH - yInter} fill={INTERMEDIATE} rx={2}>
                <title>{`Промежуточный контроль: ${w.intermediate_defects}`}</title>
              </rect>
              <rect x={x} y={yTotal} width={barW} height={yInter - yTotal} fill={FINAL} rx={2}>
                <title>{`Финальный ОТК: ${w.final_defects}`}</title>
              </rect>
              {w.checked > 0 && (
                <text x={x + barW / 2} y={yTotal - 5} textAnchor="middle" fontSize={10} fill="currentColor">
                  {w.pct}%
                </text>
              )}
              <text
                x={x + barW / 2}
                y={height - 10}
                textAnchor="middle"
                fontSize={10}
                fill="currentColor"
                fillOpacity={0.6}
              >
                {formatDate(w.week_start).slice(0, 5)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <i className="inline-block size-3 rounded-sm" style={{ background: INTERMEDIATE }} />
          Промежуточный контроль
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block size-3 rounded-sm" style={{ background: FINAL }} />
          Финальный ОТК (поздно)
        </span>
        <span>Над столбцом — доля брака от проверенного.</span>
      </figcaption>
    </figure>
  );
}

/** Парето: полоса — доля от самого частого, справа — штук и накопленная доля. */
export function ParetoBars({ rows }: { rows: QualityParetoOut[] }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">Брака за период нет.</p>;
  const top = rows[0].defects || 1;
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((row) => (
        <li key={row.name} className="grid grid-cols-[minmax(8rem,14rem)_1fr_7rem] items-center gap-2 text-sm">
          <span className="truncate" title={row.name}>
            {row.name}
          </span>
          <span className="h-2.5 overflow-hidden rounded bg-muted">
            <i className="block h-full bg-primary/70" style={{ width: `${(row.defects / top) * 100}%` }} />
          </span>
          <span className="text-xs text-muted-foreground">
            {row.defects} шт · Σ{Math.round(Number(row.cumulative_pct))}%
          </span>
        </li>
      ))}
    </ul>
  );
}
