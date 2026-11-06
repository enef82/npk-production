"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useListWorkCenters } from "@/lib/api/endpoints";
import { rub } from "@/lib/production/format";
import { PHASE_LABELS } from "@/lib/production/stages";
import { cn } from "@/lib/utils";

import { Note, Pill, TABLE } from "./bits";

/**
 * Справочник участков — только чтение: эндпоинтов правки у `production` нет, справочник
 * ведёт начальник производства в админке Django (`production.manage_reference`).
 */
export function WorkCentersView() {
  const centers = useListWorkCenters();

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-semibold">Участки</h1>
      <Note>
        Ставки, мощности и ответственные правятся в админке: раздел «Производство → Участки» (право «ведение справочников
        производства»).
      </Note>
      {centers.isLoading ? (
        <Skeleton className="h-60 w-full" />
      ) : (
        <table className={TABLE} data-testid="work-centers-table">
          <thead>
            <tr>
              <th>Код</th>
              <th>Кратко</th>
              <th>Наименование</th>
              <th>Фаза</th>
              <th className="text-right">Ставка н-ч</th>
              <th className="text-right">Мощность, чел.</th>
              <th>Ответственный</th>
              <th>Признаки</th>
            </tr>
          </thead>
          <tbody>
            {(centers.data ?? []).map((c) => (
              <tr key={c.id} className={cn(!c.is_active && "opacity-50")}>
                <td className="font-mono text-xs">{c.code}</td>
                <td>
                  <Pill tone={c.is_supply ? "y" : "n"}>{c.short_name}</Pill>
                </td>
                <td>{c.name}</td>
                <td>{PHASE_LABELS[c.phase] ?? c.phase}</td>
                <td className="text-right tabular-nums">{c.is_supply ? "—" : rub(c.hourly_rate)}</td>
                <td className="text-right">{c.capacity}</td>
                <td>{c.responsible_name || "—"}</td>
                <td className="space-x-1">
                  {c.is_supply ? <Pill tone="y">снабжение</Pill> : null}
                  {c.requires_inspection ? <Pill tone="b">точка контроля</Pill> : null}
                  {!c.is_active ? <Pill>не активен</Pill> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
