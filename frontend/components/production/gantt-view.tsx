"use client";

import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { moveProductionOperation, shiftProductionOrder, useGetProductionGantt } from "@/lib/api/endpoints";
import { fd, fdl } from "@/lib/production/dates";
import { useAction } from "@/lib/production/use-action";

import { NativeSelect, Note, TextInput } from "./bits";
import { useCards } from "./card-host";
import { GanttChart, GanttLegend } from "./gantt-chart";

/** План-график всех активных заказов (`renderGantt` прототипа). */
export function GanttView() {
  const cards = useCards();
  const { run } = useAction();
  const gantt = useGetProductionGantt();
  const [search, setSearch] = useState("");
  const [colorBy, setColorBy] = useState<"status" | "wc">("status");
  const q = search.trim().toLowerCase();
  const rows = (gantt.data ?? []).filter(
    (o) => !q || [o.number, o.customer_name, o.product_name].join(" ").toLowerCase().includes(q),
  );

  return (
    <div className="flex h-full flex-col gap-3 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">План-график</h1>
        <TextInput className="w-56" placeholder="Поиск: заказ, заказчик" value={search} onChange={(e) => setSearch(e.target.value)} />
        <NativeSelect className="w-48" value={colorBy} onChange={(e) => setColorBy(e.target.value as "status" | "wc")} aria-label="Цвет полос">
          <option value="status">Цвет: по статусу</option>
          <option value="wc">Цвет: по участку</option>
        </NativeSelect>
        <GanttLegend />
      </div>
      <p className="text-xs text-muted-foreground">
        Шкала — рабочие дни. Клик по операции или строке — карточка. Перетаскивание полосы операции — перенос (последователи
        сдвинутся по связям), полосы заказа — сдвиг всего заказа. Начатые операции не переносятся.
      </p>
      {gantt.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : rows.length ? (
        <GanttChart
          rows={rows}
          colorBy={colorBy}
          onOpenOrder={(id) => cards.openOrder(id, "plan")}
          onOpenOperation={(id) => cards.openOperation(id)}
          onMoveOperation={(op, start) =>
            void run(
              () => moveProductionOperation(op.id, { start }),
              (card) => `«${op.name}» перенесена на ${fd(card.operation.planned_start)}; окончание заказа ${fdl(card.order.planned_finish)}`,
            )
          }
          onShiftOrder={(row, days) =>
            void run(
              () => shiftProductionOrder(row.id, { days }),
              (s) => `${row.number}: план сдвинут на ${days > 0 ? "+" : ""}${days} раб. дн., окончание ${fdl(s.planned_finish)}`,
            )
          }
        />
      ) : (
        <Note>Нет активных заказов с планом.</Note>
      )}
    </div>
  );
}
