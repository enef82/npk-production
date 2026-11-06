"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { HBarList } from "@/components/charts/hbar-list";
import { Kpi, KpiRow } from "@/components/charts/kpi";
import { StackChart } from "@/components/charts/stack-chart";
import { OptionSelect } from "@/components/option-select/option-select";
import { Badge } from "@/components/ui/badge";
import { GatedButton } from "@/components/ui/gated-button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useCloseAnalyticsCutoff,
  useGetAnalyticsCutoffs,
  useReopenAnalyticsCutoff,
  type AnalyticsCutoffRowOut,
  type AnalyticsCutoffWeekOut,
} from "@/lib/api/endpoints";
import { dayMonth, planColor, pctText, toneClass, weekLabel } from "@/lib/analytics/format";
import { formatDateTime } from "@/lib/format/ru";
import { hours, num } from "@/lib/production/format";
import { cn } from "@/lib/utils";

import { CloseCutoffDialog, ReopenCutoffDialog } from "./cutoff-dialogs";

const HISTORY = [9, 13];
const DENIED = "Отсечку недели закрывает начальник производства.";

/** Экран «Отсечки» (`renderPerf` прототипа): матрица % плана, неделя, закрытие. */
export function CutoffsView() {
  const [weeks, setWeeks] = useState(9);
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const [closing, setClosing] = useState<AnalyticsCutoffWeekOut | null>(null);
  const [reopening, setReopening] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const query = useGetAnalyticsCutoffs({ weeks, week: selected }, { query: { placeholderData: (prev) => prev } });
  const data = query.data;
  const refresh = () =>
    queryClient.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/api/v1/analytics"),
    });
  const close = useCloseAnalyticsCutoff({ mutation: { onSuccess: refresh } });
  const reopen = useReopenAnalyticsCutoff({ mutation: { onSuccess: refresh } });

  const week = data?.weeks.find((w) => w.week_start === data.selected_week);
  const canClose = data?.abilities.can_close ?? false;

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4 [&>*]:shrink-0">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Недельные отсечки по участкам</h1>
        <OptionSelect
          ariaLabel="История"
          className="w-40"
          value={String(weeks)}
          onChange={(v) => setWeeks(Number(v))}
          options={HISTORY.map((n) => ({ value: String(n), label: `${n - 1} недель + текущая` }))}
        />
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        Отсечка фиксирует итоги недели по участку: плановые нормо-часы, освоенные (закрытые прогрессом и визами),
        отработанные часы из табеля и брак. После закрытия цифры недели не меняются. Клик по ячейке — детали недели.
      </p>

      {data && (
        <section className="overflow-x-auto rounded-lg border p-3">
          <Table data-testid="cutoff-matrix">
            <TableHeader>
              <TableRow>
                <TableHead>Участок · % выполнения плана</TableHead>
                {data.weeks.map((w) => (
                  <TableHead
                    key={w.week_start}
                    className={cn("text-center", w.week_start === data.selected_week && "text-primary")}
                  >
                    {dayMonth(w.week_start)}
                    <div className="text-[10px] font-normal text-muted-foreground">
                      {w.status === "current" ? "текущая" : w.status === "closed" ? "отсечка" : "открыта"}
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.weeks[0]?.rows.map((r, i) => (
                <TableRow key={r.work_center_id}>
                  <TableCell>{r.name}</TableCell>
                  {data.weeks.map((w) => {
                    const cell = w.rows[i];
                    return (
                      <TableCell
                        key={w.week_start}
                        className={cn(
                          "cursor-pointer text-center tabular-nums",
                          w.week_start === data.selected_week && "outline-2 -outline-offset-2 outline-primary",
                        )}
                        style={{ background: planColor(cell?.plan_pct) }}
                        title={`План ${hours(cell?.planned)} н-ч · освоено ${hours(cell?.earned)} н-ч`}
                        onClick={() => setSelected(w.week_start)}
                      >
                        {pctText(cell?.plan_pct)}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-lg border p-3">
            <h2 className="mb-2 font-semibold">История: освоено против плана, н-ч</h2>
            <StackChart
              categories={data.weeks.map((w) => dayMonth(w.week_start))}
              series={[{ name: "Освоено", color: "#2f5bd3", values: data.weeks.map((w) => num(w.total.earned)) }]}
              line={{ name: "План", values: data.weeks.map((w) => num(w.total.planned)) }}
              topLabels={data.weeks.map((w) => pctText(w.total.plan_pct))}
              highlight={data.weeks.findIndex((w) => w.week_start === data.selected_week)}
              onCategoryClick={(i) => setSelected(data.weeks[i].week_start)}
              height={230}
            />
            <p className="mt-1 text-xs text-muted-foreground">Над столбцом — выполнение плана недели.</p>
          </section>
          <section className="rounded-lg border p-3">
            <h2 className="mb-2 font-semibold">Выработка участков за неделю {week && weekLabel(week.week_start)}</h2>
            <HBarList
              unit="%"
              emptyText="Нет отработанных часов за неделю."
              rows={(week?.rows ?? [])
                .filter((r) => r.output_pct !== null)
                .map((r) => ({
                  label: r.name,
                  value: Math.round(num(r.output_pct)),
                  color: num(r.output_pct) >= 85 ? "#3f9b6b" : num(r.output_pct) >= 65 ? "#e0a526" : "#c53030",
                }))}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Выработка = освоенные нормо-часы ÷ отработанные часы. Ниже 85% — потери времени (простои, ожидание
              материалов, переделки).
            </p>
          </section>
        </div>
      )}

      {week && data && (
        <section className="rounded-lg border p-3" data-testid="cutoff-week">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">Неделя {weekLabel(week.week_start)}</h2>
            {week.status === "closed" ? (
              <>
                <Badge variant="secondary" data-testid="cutoff-closed">
                  отсечка закрыта · {week.closed_by_name} · {formatDateTime(week.closed_at)}
                </Badge>
                {week.comment && <span className="text-xs text-muted-foreground">«{week.comment}»</span>}
                <span className="ml-auto" />
                <GatedButton
                  size="sm"
                  variant="outline"
                  allowed={canClose}
                  reason={DENIED}
                  onClick={() => setReopening(week.week_start)}
                >
                  Переоткрыть
                </GatedButton>
              </>
            ) : (
              <>
                <Badge variant="outline" className="border-amber-400 text-amber-800">
                  открыта — данные текущие
                </Badge>
                <span className="ml-auto" />
                <GatedButton size="sm" allowed={canClose} reason={DENIED} onClick={() => setClosing(week)}>
                  Закрыть отсечку недели
                </GatedButton>
              </>
            )}
          </div>
          <KpiRow>
            <Kpi value={`${hours(week.total.planned)} н-ч`} label="план" />
            <Kpi value={`${hours(week.total.earned)} н-ч`} label="освоено" />
            <Kpi
              value={pctText(week.total.plan_pct)}
              label="выполнение плана"
              tone={tone(week.total.plan_pct, 95, 80)}
            />
            <Kpi value={week.total.worked === null ? "—" : `${hours(week.total.worked)} ч`} label="отработано" />
            <Kpi value={pctText(week.total.output_pct)} label="выработка" tone={tone(week.total.output_pct, 85, 65)} />
            <Kpi value={pctText(week.total.load_pct)} label="загрузка (план ÷ мощность)" />
          </KpiRow>
          <div className="mt-3 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Участок</TableHead>
                  <TableHead className="text-right">Мощность, ч</TableHead>
                  <TableHead className="text-right">План, н-ч</TableHead>
                  <TableHead className="text-right">Освоено, н-ч</TableHead>
                  <TableHead className="text-right">% плана</TableHead>
                  <TableHead className="text-right">Отработано, ч</TableHead>
                  <TableHead className="text-right" title="Освоено ÷ отработано">
                    Выработка
                  </TableHead>
                  <TableHead className="text-right" title="План ÷ мощность">
                    Загрузка
                  </TableHead>
                  <TableHead className="text-right">Проверено</TableHead>
                  <TableHead className="text-right">Брак</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {week.rows.map((r) => (
                  <WeekRow key={r.work_center_id} row={r} />
                ))}
                <WeekRow row={week.total} total />
              </TableBody>
            </Table>
          </div>
          {data.events.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-sm font-semibold">Журнал отсечки</h3>
              <ul className="text-xs text-muted-foreground" data-testid="cutoff-events">
                {data.events.map((e) => (
                  <li key={`${e.created_at}-${e.action}`}>
                    {formatDateTime(e.created_at)} · {e.action_label} · {e.actor_name}
                    {e.text && ` · «${e.text}»`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {!data && <p className="text-sm text-muted-foreground">{query.isError ? "Не удалось загрузить отсечки." : "Загрузка…"}</p>}

      <CloseCutoffDialog
        week={closing}
        onClose={() => setClosing(null)}
        onConfirm={async (comment, worked) => {
          if (!closing) return;
          await close.mutateAsync({ data: { week_start: closing.week_start, comment, worked } });
          toast.success("Отсечка недели закрыта");
          setClosing(null);
        }}
      />
      <ReopenCutoffDialog
        week={reopening}
        onClose={() => setReopening(null)}
        onConfirm={async (reason) => {
          if (!reopening) return;
          await reopen.mutateAsync({ weekStart: reopening, data: { reason } });
          toast.success("Отсечка переоткрыта");
          setReopening(null);
        }}
      />
    </div>
  );
}

function tone(value: string | null, good: number, warn: number): "ok" | "warn" | "bad" | undefined {
  if (value === null) return undefined;
  const v = num(value);
  return v >= good ? "ok" : v >= warn ? "warn" : "bad";
}

function WeekRow({ row, total }: { row: AnalyticsCutoffRowOut; total?: boolean }) {
  return (
    <TableRow className={cn(total && "bg-muted/40 font-semibold")}>
      <TableCell>{row.name}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(row.capacity)}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(row.planned)}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(row.earned)}</TableCell>
      <TableCell className={cn("text-right font-semibold tabular-nums", toneClass(row.plan_pct, 95, 80))}>
        {pctText(row.plan_pct)}
      </TableCell>
      <TableCell className="text-right tabular-nums">{row.worked === null ? "—" : hours(row.worked)}</TableCell>
      <TableCell className="text-right tabular-nums">{pctText(row.output_pct)}</TableCell>
      <TableCell className="text-right tabular-nums">{pctText(row.load_pct)}</TableCell>
      <TableCell className="text-right tabular-nums">{row.checked || "—"}</TableCell>
      <TableCell className={cn("text-right tabular-nums", row.defects > 0 && "text-destructive")}>
        {row.checked ? `${num(row.defect_pct).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%` : "—"}
      </TableCell>
    </TableRow>
  );
}
