/** Горизонтальные полосы «подпись — полоса — значение» (Парето простоев, категории). */
export function HBarList({
  rows,
  unit = "ч",
  emptyText = "Нет данных.",
}: {
  rows: { label: string; value: number; color?: string }[];
  unit?: string;
  emptyText?: string;
}) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="grid grid-cols-[minmax(8rem,auto)_1fr_auto] items-center gap-x-3 gap-y-1.5 text-sm">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <span className="truncate">{row.label}</span>
          <div className="h-2.5 rounded-full bg-muted">
            <div
              className="h-2.5 rounded-full"
              style={{ width: `${(row.value / max) * 100}%`, background: row.color ?? "#e0a526" }}
            />
          </div>
          <span className="text-right text-muted-foreground tabular-nums">
            {row.value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} {unit}
          </span>
        </div>
      ))}
    </div>
  );
}
