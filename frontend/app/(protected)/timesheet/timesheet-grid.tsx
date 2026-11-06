"use client";

import { Fragment } from "react";

import type { GridCellOut, MonthGridOut } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

import { hours, objectLabel, weekdayOf } from "./labels";

function cellView(cell: GridCellOut, weekend: boolean): { text: React.ReactNode; className: string } {
  if (cell.absence_code) return { text: cell.absence_code, className: "bg-blue-50 text-blue-900" };
  if (cell.is_trip) return { text: "К", className: "bg-emerald-50 text-emerald-900" };
  const work = cell.work_hours !== "0" && cell.work_hours !== "0.00";
  const overtime = cell.overtime_hours !== "0" && cell.overtime_hours !== "0.00";
  if (work || overtime) {
    return {
      text: (
        <>
          {hours(cell.work_hours)}
          {overtime && <sup className="text-[9px] text-red-700">+{hours(cell.overtime_hours)}</sup>}
        </>
      ),
      className: cn(cell.has_overhead && "bg-amber-50", weekend && !cell.has_overhead && "bg-muted/70"),
    };
  }
  if (cell.is_missing) return { text: "?", className: "bg-red-100 font-semibold text-red-700" };
  return { text: "", className: weekend ? "bg-muted/70" : "" };
}

function deltaClass(delta: string): string {
  if (delta.startsWith("-")) return "text-red-600";
  if (/^0(\.0+)?$/.test(delta)) return "text-emerald-600";
  return "text-amber-600";
}

/** Сетка «сотрудник × день» (renderTimesheet прототипа): коды и часы, итог, норма, Δ. */
export function TimesheetGrid({
  grid,
  expand,
  onCellClick,
}: {
  grid: MonthGridOut;
  expand: boolean;
  onCellClick: (employeeId: string, day: string) => void;
}) {
  const weekend = new Map(grid.days.map((d) => [d.date, d.is_weekend]));
  return (
    <div className="overflow-auto rounded-xl border">
      <table className="w-full border-collapse text-xs" data-testid="timesheet-grid">
        <thead className="bg-muted/50">
          <tr>
            <th className="sticky left-0 z-10 min-w-52 bg-muted px-2 py-1.5 text-left font-medium">Сотрудник</th>
            {grid.days.map((d) => (
              <th
                key={d.date}
                className={cn("min-w-8 px-0.5 py-1 text-center font-medium", d.is_weekend && "text-muted-foreground")}
              >
                {Number(d.date.slice(8))}
                <br />
                <span className="font-normal text-muted-foreground">{weekdayOf(d.date)}</span>
              </th>
            ))}
            <th className="px-2 text-right font-medium">Итого</th>
            <th className="px-2 text-right font-medium">Норма</th>
            <th className="px-2 text-right font-medium">Δ</th>
          </tr>
        </thead>
        <tbody>
          {grid.rows.map((row) => (
            <Fragment key={row.employee_id}>
              <tr className="border-t">
                <td className="sticky left-0 z-10 bg-background px-2 py-1">
                  <div className="font-medium">{row.full_name}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {row.position} · таб. {row.personnel_no}
                  </div>
                </td>
                {row.cells.map((cell) => {
                  const view = cellView(cell, weekend.get(cell.date) ?? false);
                  return (
                    <td
                      key={cell.date}
                      data-employee={row.employee_id}
                      data-day={cell.date}
                      className={cn(
                        "cursor-pointer border-l px-0.5 py-1 text-center tabular-nums hover:outline hover:outline-1 hover:outline-primary",
                        view.className,
                      )}
                      onClick={() => onCellClick(row.employee_id, cell.date)}
                    >
                      {view.text}
                    </td>
                  );
                })}
                <td className="border-l px-2 text-right font-semibold tabular-nums">{hours(row.total)}</td>
                <td className="px-2 text-right text-muted-foreground tabular-nums">{hours(row.norm)}</td>
                <td className={cn("px-2 text-right tabular-nums", deltaClass(row.delta))}>
                  {/^0(\.0+)?$/.test(row.delta) ? "✓" : `${row.delta.startsWith("-") ? "" : "+"}${hours(row.delta)}`}
                </td>
              </tr>
              {expand &&
                row.objects.map((obj) => {
                  const byDay = new Map(obj.days.map((d) => [d.date, d.hours]));
                  return (
                    <tr key={`${obj.target}-${obj.order_id ?? ""}`} className="bg-muted/20 text-muted-foreground">
                      <td className="sticky left-0 z-10 bg-muted px-2 py-0.5 pl-4">
                        └ {objectLabel(obj.target, obj.order_label)}
                      </td>
                      {grid.days.map((d) => (
                        <td key={d.date} className="border-l px-0.5 text-center tabular-nums">
                          {hours(byDay.get(d.date))}
                        </td>
                      ))}
                      <td className="border-l px-2 text-right tabular-nums">{hours(obj.total)}</td>
                      <td />
                      <td />
                    </tr>
                  );
                })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
