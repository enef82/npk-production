"use client";

import { useState } from "react";

import { HBarList } from "@/components/charts/hbar-list";
import { Kpi, KpiRow } from "@/components/charts/kpi";
import { NativeSelect } from "@/components/ui/native-select";
import { useGetEquipmentDashboard, useListEquipment } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

import { useNames } from "./equipment-view";
import {
  EQUIPMENT_STATUS_LABELS,
  EQUIPMENT_STATUS_TONE,
  MAINTENANCE_TONE,
  num,
  pct,
  shortDate,
  utilBg,
  utilClass,
} from "./labels";

function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border bg-card p-4", className)}>
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function MachinesTab({ onOpenMachine }: { onOpenMachine: (id: string) => void }) {
  const [week, setWeek] = useState<string | undefined>(undefined);
  const dashboard = useGetEquipmentDashboard(week ? { week } : undefined);
  const selected = week ?? dashboard.data?.week_start;
  const machines = useListEquipment(selected ? { week: selected } : undefined, {
    query: { enabled: Boolean(selected) },
  });
  const names = useNames();
  const d = dashboard.data;

  return (
    <div className="flex flex-col gap-4">
      {d && (
        <KpiRow>
          <Kpi value={d.kpi.equipment_count} label="единиц оборудования" />
          <Kpi value={pct(d.kpi.utilization)} label={`загрузка за неделю ${shortDate(d.week_start)}`} />
          <Kpi value={`${num(d.kpi.idle_and_down_hours, 0)} ч`} label="простои и отказы за неделю" />
          <Kpi value={d.kpi.maintenance_overdue} label="ТО просрочено" tone={d.kpi.maintenance_overdue ? "bad" : undefined} />
          <Kpi value={d.kpi.maintenance_soon} label="ТО в ближайшие 10%" tone={d.kpi.maintenance_soon ? "warn" : undefined} />
        </KpiRow>
      )}

      <Panel title="Оборудование, наработка и ТО">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Неделя</span>
          <NativeSelect
            aria-label="Неделя"
            className="w-36"
            value={selected ?? ""}
            onChange={(e) => setWeek(e.target.value)}
          >
            {d?.weeks.map((w) => (
              <option key={w} value={w}>
                с {shortDate(w)}
              </option>
            ))}
          </NativeSelect>
          <span className="text-xs text-muted-foreground">
            Наработку вносит мастер за смену; ТО планируется по моточасам от последнего ТО.
          </span>
        </div>
        <div className="overflow-auto">
          <table className="w-full text-sm" data-testid="machines-table">
            <thead className="text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="py-1.5 font-medium">Инв. №</th>
                <th className="font-medium">Станок</th>
                <th className="font-medium">Участок</th>
                <th className="font-medium">Подключение</th>
                <th className="text-right font-medium">Моточасы</th>
                <th className="text-right font-medium">За неделю, ч</th>
                <th className="text-right font-medium">Загрузка</th>
                <th className="text-right font-medium">Простой</th>
                <th className="pl-3 font-medium">Ближайшее ТО</th>
                <th className="font-medium">Состояние</th>
              </tr>
            </thead>
            <tbody>
              {machines.data?.map((m) => {
                const t = m.nearest_maintenance;
                const center = m.work_center_id ? names.workCenter.get(m.work_center_id) : undefined;
                return (
                  <tr
                    key={m.id}
                    className="cursor-pointer border-t hover:bg-muted/40"
                    onClick={() => onOpenMachine(m.id)}
                  >
                    <td className="py-1.5 text-muted-foreground">{m.inventory_no}</td>
                    <td>
                      <span className="font-medium text-primary underline-offset-2 hover:underline">{m.name}</span>
                      <div className="text-xs text-muted-foreground">{m.control_system}</div>
                    </td>
                    <td>
                      {center ? (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-xs" title={center.name}>
                          {center.short_name}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">общее</span>
                      )}
                    </td>
                    <td className="max-w-44 text-xs text-muted-foreground">{m.connection}</td>
                    <td className="text-right tabular-nums">{num(m.operating_hours, 0)}</td>
                    <td className="text-right tabular-nums">{num(m.week.run)}</td>
                    <td className={cn("text-right font-semibold tabular-nums", utilClass(m.week.utilization))}>
                      {m.week.days ? pct(m.week.utilization) : "—"}
                    </td>
                    <td className="text-right tabular-nums">{num(Number(m.week.idle) + Number(m.week.down))}</td>
                    <td className="pl-3 text-xs">
                      {t && (
                        <span className="inline-flex items-center gap-1.5">
                          <span className={cn("rounded px-1.5 py-0.5 font-medium", MAINTENANCE_TONE[t.state])}>{t.code}</span>
                          {Number(t.hours_left) <= 0 ? (
                            <b className="text-red-600">просрочено</b>
                          ) : (
                            <span>
                              через {num(t.hours_left, 0)} ч · ~{shortDate(t.due_date)}
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", EQUIPMENT_STATUS_TONE[m.status])}>
                        {EQUIPMENT_STATUS_LABELS[m.status]}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {d && (
        <Panel title="Загрузка оборудования по неделям">
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="py-1 text-left font-medium text-muted-foreground">
                    Станок · загрузка смены (работа под нагрузкой)
                  </th>
                  {d.weeks.map((w) => (
                    <th key={w} className={cn("px-1 font-medium", w === selected ? "text-primary" : "text-muted-foreground")}>
                      {shortDate(w)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.matrix.map((row) => (
                  <tr key={row.equipment_id}>
                    <td className="py-0.5 pr-2">{row.name}</td>
                    {row.weeks.map((w) => (
                      <td
                        key={w.week_start}
                        className={cn(
                          "cursor-pointer border border-background px-1 text-center tabular-nums",
                          w.week_start === selected && "outline outline-2 -outline-offset-2 outline-primary",
                        )}
                        style={{ background: utilBg(w.utilization, w.days) }}
                        title={`Работа ${num(w.run)} ч · наладка ${num(w.setup)} · простой ${num(w.idle)} · отказ ${num(w.down)}`}
                        onClick={() => setWeek(w.week_start)}
                      >
                        {w.days ? pct(w.utilization) : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Клик по неделе — пересчёт сводки. Ниже 50% — оборудование простаивает: проверьте причины.
          </p>
        </Panel>
      )}

      {d && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title={`Причины простоев (Парето), неделя ${shortDate(d.week_start)}`}>
            <HBarList
              rows={d.pareto.map((p) => ({
                label: p.reason,
                value: Number(p.hours),
                color: p.is_down ? "#c53030" : "#e0a526",
              }))}
            />
          </Panel>
          <Panel title="План ТО на 30 дней">
            {d.maintenance_plan.length === 0 ? (
              <p className="text-sm text-muted-foreground">ТО в ближайший месяц не требуется.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="text-left">
                    <th className="py-1 font-medium">Дата</th>
                    <th className="font-medium">Станок</th>
                    <th className="font-medium">Вид</th>
                    <th className="font-medium">Работы</th>
                  </tr>
                </thead>
                <tbody>
                  {d.maintenance_plan.map((p) => (
                    <tr
                      key={`${p.equipment_id}-${p.maintenance.maintenance_type_id}`}
                      className="cursor-pointer border-t hover:bg-muted/40"
                      onClick={() => onOpenMachine(p.equipment_id)}
                    >
                      <td className="py-1">
                        <span className={cn("rounded px-1.5 py-0.5 text-xs", MAINTENANCE_TONE[p.maintenance.state])}>
                          {p.maintenance.state === "overdue" ? "сейчас" : shortDate(p.maintenance.due_date)}
                        </span>
                      </td>
                      <td>{p.equipment_name}</td>
                      <td>{p.maintenance.code}</td>
                      <td className="text-xs text-muted-foreground">{p.maintenance.scope}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
