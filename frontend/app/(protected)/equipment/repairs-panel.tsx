"use client";

import { useState } from "react";
import { Plus } from "lucide-react";

import { HBarList } from "@/components/charts/hbar-list";
import { Kpi, KpiRow } from "@/components/charts/kpi";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { useListEquipment, useListRepairs, type RepairKind } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

import {
  REPAIR_KIND_LABELS,
  REPAIR_KIND_TONE,
  REPAIR_STATUS_LABELS,
  REPAIR_STATUS_TONE,
  formatLocal,
  num,
} from "./labels";
import type { RepairDraft } from "./repair-dialog";

/** Журнал аварий и ремонтов со сводкой (repairsPanel прототипа). */
export function RepairsPanel({ onOpenRepair }: { onOpenRepair: (draft: RepairDraft) => void }) {
  const [days, setDays] = useState(90);
  const [kind, setKind] = useState<RepairKind | "">("");
  const [equipmentId, setEquipmentId] = useState("");
  const machines = useListEquipment();
  const journal = useListRepairs({ days, kind: kind || undefined, equipment_id: equipmentId || undefined });
  const s = journal.data?.summary;

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Журнал аварий и ремонтов</h2>
        <NativeSelect aria-label="Период" className="w-28" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[30, 90, 180].map((n) => (
            <option key={n} value={n}>
              {n} дней
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Вид"
          className="w-44"
          value={kind}
          onChange={(e) => setKind(e.target.value as RepairKind | "")}
        >
          <option value="">Все виды</option>
          {Object.entries(REPAIR_KIND_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Оборудование в журнале"
          className="w-72"
          value={equipmentId}
          onChange={(e) => setEquipmentId(e.target.value)}
        >
          <option value="">Всё оборудование</option>
          {machines.data?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </NativeSelect>
        <span className="flex-1" />
        {journal.data?.can_register && (
          <Button
            size="sm"
            onClick={() => onOpenRepair({ mode: "new", equipmentId: equipmentId || undefined, kind: "fail" })}
          >
            <Plus aria-hidden />
            Авария / ремонт
          </Button>
        )}
      </div>

      {s && (
        <KpiRow>
          <Kpi value={s.failures} label="аварий" tone={s.failures ? "bad" : undefined} />
          <Kpi value={`${num(s.failure_downtime)} ч`} label="простой из-за аварий" />
          <Kpi value={`${num(s.labor_hours)} чел·ч`} label="трудозатраты на ремонты и ТО" />
          <Kpi value={`${num(s.mttr)} ч`} label="MTTR" title="Среднее время восстановления" />
          <Kpi
            value={s.mtbf ? `${num(s.mtbf, 0)} ч` : "—"}
            label="MTBF"
            title="Средняя наработка на отказ, машино-часы работы"
          />
        </KpiRow>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full text-sm" data-testid="repairs-table">
            <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="py-1.5 font-medium">№</th>
                <th className="font-medium">Оборудование</th>
                <th className="font-medium">Вид</th>
                <th className="font-medium">Начало</th>
                <th className="text-right font-medium">Простой</th>
                <th className="pl-3 font-medium">Описание</th>
                <th className="text-right font-medium">Чел·ч</th>
                <th className="pl-3 font-medium">Статус</th>
              </tr>
            </thead>
            <tbody>
              {journal.data?.items.map((r) => (
                <tr
                  key={r.id}
                  className={cn("cursor-pointer border-t align-top hover:bg-muted/40", r.status !== "done" && "bg-red-50/60")}
                  onClick={() => onOpenRepair({ mode: "edit", id: r.id })}
                >
                  <td className="py-1.5 text-xs text-muted-foreground">{r.number}</td>
                  <td>
                    {r.equipment_name}
                    <div className="text-xs text-muted-foreground">{r.equipment_inventory_no}</div>
                  </td>
                  <td>
                    <span className={cn("rounded px-1.5 py-0.5 text-xs", REPAIR_KIND_TONE[r.kind])}>
                      {REPAIR_KIND_LABELS[r.kind]}
                    </span>
                    {r.category_name && <div className="text-xs text-muted-foreground">{r.category_name}</div>}
                  </td>
                  <td className="whitespace-nowrap text-xs">{formatLocal(r.started_at)}</td>
                  <td className="text-right tabular-nums">{num(r.downtime_hours)} ч</td>
                  <td className="pl-3">
                    {r.description}
                    {r.fix && <div className="text-xs text-muted-foreground">{r.fix}</div>}
                  </td>
                  <td className="text-right tabular-nums">{num(r.labor_hours)}</td>
                  <td className="pl-3">
                    <span className={cn("rounded px-1.5 py-0.5 text-xs whitespace-nowrap", REPAIR_STATUS_TONE[r.status])}>
                      {REPAIR_STATUS_LABELS[r.status]}
                    </span>
                  </td>
                </tr>
              ))}
              {journal.data && journal.data.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-2 text-sm text-muted-foreground">
                    Записей нет.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <h3 className="mb-2 text-sm font-semibold">Простой по категориям отказов</h3>
            <HBarList
              rows={(s?.downtime_by_category ?? []).map((c) => ({
                label: c.category,
                value: Number(c.hours),
                color: "#c53030",
              }))}
              emptyText="Нет аварий за период."
            />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Аварий по оборудованию</h3>
            {(s?.failures_by_equipment ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">—</p>
            ) : (
              <ul className="flex flex-col gap-1 text-sm">
                {s?.failures_by_equipment.map((f) => (
                  <li key={f.equipment_id} className="flex justify-between gap-2 border-b pb-1">
                    <span>{f.equipment_name}</span>
                    <b>{f.failures}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Часы исполнителей при закрытии записи переносятся в табель на объект «Ремонт и ТО оборудования».
          </p>
        </div>
      </div>
    </section>
  );
}
