"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGetAnalyticsLoad } from "@/lib/api/endpoints";
import { dayMonth, loadColor } from "@/lib/analytics/format";
import { hours, num } from "@/lib/production/format";

const LEGEND: [string, number][] = [
  ["нет работ", 0],
  ["до 50%", 0.3],
  ["50–85%", 0.7],
  ["85–100%", 0.95],
  ["перегрузка", 1.2],
];

/** Загрузка участков на 10 недель (`renderLoad` прототипа). */
export function LoadView() {
  const query = useGetAnalyticsLoad();
  const data = query.data;
  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4 [&>*]:shrink-0">
      <h1 className="text-lg font-semibold">Загрузка участков на 10 недель</h1>
      <p className="-mt-2 text-xs text-muted-foreground">
        Часы по участкам на 10 недель: остаток операций заказов в работе (твёрдо) + предварительные планы заявок (в
        скобках). Мощность = исполнители × 40 ч. Красное — перегрузка.
      </p>
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {LEGEND.map(([label, ratio]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <i className="inline-block size-3 rounded-sm border" style={{ background: loadColor(ratio) }} />
            {label}
          </span>
        ))}
      </div>
      {data ? (
        <section className="overflow-x-auto rounded-lg border p-3">
          <Table data-testid="load-grid">
            <TableHeader>
              <TableRow>
                <TableHead>Участок</TableHead>
                <TableHead className="text-right">Мощн.</TableHead>
                {data.weeks.map((w) => (
                  <TableHead key={w} className="text-center">
                    {dayMonth(w)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row) => (
                <TableRow key={row.work_center_id}>
                  <TableCell className="whitespace-nowrap">{row.name}</TableCell>
                  <TableCell className="text-right text-xs text-muted-foreground">{hours(row.capacity)} ч</TableCell>
                  {row.cells.map((cell, i) => {
                    const total = num(cell.total);
                    const ratio = num(row.capacity) ? total / num(row.capacity) : 0;
                    return (
                      <TableCell
                        key={data.weeks[i]}
                        className="min-w-16 text-center tabular-nums"
                        style={{ background: loadColor(ratio) }}
                        title={`Заказы: ${Math.round(num(cell.firm))} ч · заявки: ${Math.round(num(cell.tentative))} ч · загрузка ${Math.round(num(cell.pct))}%`}
                      >
                        {total >= 0.5 ? `${Math.round(num(cell.pct))}%` : ""}
                        {num(cell.tentative) >= 1 && (
                          <div className="text-[10px] text-muted-foreground">({Math.round(num(cell.tentative))} ч)</div>
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">{query.isError ? "Не удалось загрузить загрузку." : "Загрузка…"}</p>
      )}
    </div>
  );
}
