"use client";

import { useState } from "react";

import { OptionSelect } from "@/components/option-select/option-select";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useGetQualityReference,
  useGetQualitySummary,
  useListInspectionRecords,
  type ListInspectionRecordsParams,
} from "@/lib/api/endpoints";
import { formatDate, formatNumber } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import { ParetoBars, WeeklyDefectsChart } from "./charts";

const PERIODS = [4, 8, 12];

function pctTone(pct: number): string {
  if (pct > 4) return "text-destructive";
  if (pct > 2) return "text-amber-700";
  return "text-emerald-700";
}

/** Экран «Качество» (`renderQuality` прототипа). */
export function QualityView() {
  const [weeks, setWeeks] = useState(8);
  const summary = useGetQualitySummary({ weeks }, { query: { placeholderData: (prev) => prev } });
  const reference = useGetQualityReference();
  const data = summary.data;
  const kpi = data?.kpi;

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Качество</h1>
        <span className="text-xs text-muted-foreground">
          Промежуточный контроль встроен в операции участков; результаты вносятся в карточке операции.
        </span>
        <OptionSelect
          ariaLabel="Период"
          className="w-36"
          value={String(weeks)}
          onChange={(v) => setWeeks(Number(v))}
          options={PERIODS.map((n) => ({ value: String(n), label: `${n} недель` }))}
        />
      </div>
      {data && (
        <p className="-mt-2 text-xs text-muted-foreground">
          Период: {formatDate(data.date_from)} — {formatDate(data.date_to)}
        </p>
      )}

      {kpi && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="quality-kpi">
          <Kpi value={formatNumber(kpi.checked)} label="проверено, шт." />
          <Kpi value={`${kpi.defects} · ${kpi.pct}%`} label="брак" tone="text-destructive" />
          <Kpi value={String(kpi.rework)} label="исправимый (доработка)" />
          <Kpi value={String(kpi.scrap)} label="неисправимый (списание)" />
          <Kpi value={`${Math.round(Number(kpi.early_pct))}%`} label="выявлено до финального ОТК" tone="text-emerald-700" />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border p-3">
          <h2 className="mb-2 font-semibold">Брак по неделям: где выявлен (12 недель)</h2>
          {data ? <WeeklyDefectsChart weeks={data.dynamics} /> : <p className="text-sm text-muted-foreground">Загрузка…</p>}
          <p className="mt-2 text-xs text-muted-foreground">
            Чем больше синего и меньше красного, тем раньше ловим брак и дешевле его исправление.
          </p>
        </section>
        <section className="flex flex-col gap-3 rounded-lg border p-3">
          <div>
            <h2 className="mb-2 font-semibold">Причины брака (Парето)</h2>
            <ParetoBars rows={data?.pareto_causes ?? []} />
            {kpi && Number(kpi.defects) > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">По вине оператора — {kpi.operator_pct}% брака.</p>
            )}
          </div>
          <div>
            <h2 className="mb-2 font-semibold">Виды дефектов</h2>
            <ParetoBars rows={data?.pareto_defect_types ?? []} />
          </div>
        </section>
      </div>

      <section className="rounded-lg border p-3">
        <h2 className="mb-2 font-semibold">По точкам контроля</h2>
        <div className="overflow-x-auto">
          <Table data-testid="quality-by-work-center">
            <TableHeader>
              <TableRow>
                <TableHead>Участок</TableHead>
                <TableHead>Точка контроля</TableHead>
                <TableHead className="text-right">Проверено</TableHead>
                <TableHead className="text-right">Брак</TableHead>
                <TableHead className="text-right">%</TableHead>
                <TableHead className="text-right">Доработка</TableHead>
                <TableHead className="text-right">Списание</TableHead>
                <TableHead>Главный дефект</TableHead>
                <TableHead className="text-right">Тренд</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.by_work_center ?? []).map((row) => {
                const trend = Number(row.trend);
                return (
                  <TableRow key={row.work_center_id}>
                    <TableCell>{row.work_center_name}</TableCell>
                    <TableCell>
                      {row.point_name} {row.is_final && <Badge variant="secondary">финальный</Badge>}
                    </TableCell>
                    <TableCell className="text-right">{formatNumber(row.checked)}</TableCell>
                    <TableCell className="text-right">{row.defects}</TableCell>
                    <TableCell className={cn("text-right font-semibold", pctTone(Number(row.pct)))}>{row.pct}%</TableCell>
                    <TableCell className="text-right">{row.rework}</TableCell>
                    <TableCell className="text-right">{row.scrap}</TableCell>
                    <TableCell>
                      {row.top_defect ? (
                        <>
                          {row.top_defect.name}{" "}
                          <span className="text-xs text-muted-foreground">({row.top_defect.defects})</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right",
                        trend > 0.3 ? "text-destructive" : trend < -0.3 ? "text-emerald-700" : "text-muted-foreground",
                      )}
                    >
                      {trend > 0.3 ? "▲" : trend < -0.3 ? "▼" : "▬"} {Math.abs(trend).toFixed(1)} п.п.
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </section>

      <RecordsJournal
        points={(reference.data?.points ?? []).map((p) => ({ value: p.work_center_id, label: p.work_center_name }))}
        causes={(reference.data?.causes ?? []).map((c) => ({ value: c.id, label: c.name }))}
      />
    </div>
  );
}

function Kpi({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <div className="flex flex-col rounded-lg border px-4 py-3">
      <b className={cn("text-xl", tone)}>{value}</b>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

type OptionList = { value: string; label: string }[];

function RecordsJournal({ points, causes }: { points: OptionList; causes: OptionList }) {
  const [workCenter, setWorkCenter] = useState("");
  const [cause, setCause] = useState("");
  const [defectsOnly, setDefectsOnly] = useState(true);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const params: ListInspectionRecordsParams = {
    work_center_id: workCenter || undefined,
    cause_id: cause || undefined,
    defects_only: defectsOnly,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    limit: 200,
  };
  const records = useListInspectionRecords(params, { query: { placeholderData: (prev) => prev } });
  const rows = records.data ?? [];

  return (
    <section className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-2 font-semibold">Журнал записей контроля</h2>
        <OptionSelect
          ariaLabel="Участок"
          className="w-56"
          value={workCenter}
          onChange={setWorkCenter}
          emptyLabel="Все участки"
          options={points}
        />
        <OptionSelect
          ariaLabel="Причина"
          className="w-48"
          value={cause}
          onChange={setCause}
          emptyLabel="Все причины"
          options={causes}
        />
        <label className="flex items-center gap-1.5 text-sm">
          <Checkbox checked={defectsOnly} onCheckedChange={(on) => setDefectsOnly(!!on)} aria-label="Только с браком" />
          только с браком
        </label>
        <Input
          type="date"
          className="h-8 w-40"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="С даты"
        />
        <Input type="date" className="h-8 w-40" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label="По дату" />
        <span className="text-xs text-muted-foreground">{rows.length} записей</span>
      </div>
      <div className="overflow-x-auto">
        <Table data-testid="quality-records">
          <TableHeader>
            <TableRow>
              <TableHead>Дата</TableHead>
              <TableHead>Заказ</TableHead>
              <TableHead>Операция</TableHead>
              <TableHead>Участок</TableHead>
              <TableHead className="text-right">Пров.</TableHead>
              <TableHead className="text-right">Дораб.</TableHead>
              <TableHead className="text-right">Спис.</TableHead>
              <TableHead>Дефект</TableHead>
              <TableHead>Причина</TableHead>
              <TableHead>Контролёр</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={10} className="text-muted-foreground">
                  {records.isLoading ? "Загрузка…" : "Записей нет."}
                </TableCell>
              </TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{formatDate(r.date)}</TableCell>
                <TableCell>
                  <div className="font-medium">{r.order_number}</div>
                  <div className="text-xs text-muted-foreground">{r.customer_name}</div>
                </TableCell>
                <TableCell className="max-w-56 whitespace-normal">{r.operation_name}</TableCell>
                <TableCell className="text-xs">{r.work_center_name}</TableCell>
                <TableCell className="text-right">{r.checked}</TableCell>
                <TableCell className={r.rework ? "text-right font-semibold text-amber-700" : "text-right"}>{r.rework}</TableCell>
                <TableCell className={r.scrap ? "text-right font-semibold text-destructive" : "text-right"}>{r.scrap}</TableCell>
                <TableCell className="max-w-56 whitespace-normal">
                  {r.defect_type_name || "—"}
                  {r.comment && <div className="text-xs text-muted-foreground">{r.comment}</div>}
                </TableCell>
                <TableCell>{r.cause_name || "—"}</TableCell>
                <TableCell>{r.inspector_name}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
