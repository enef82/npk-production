"use client";

import { useState } from "react";

import { Kpi, KpiRow } from "@/components/charts/kpi";
import { OptionSelect } from "@/components/option-select/option-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useGetAnalyticsEmployees,
  type AnalyticsEmployeeRowOut,
  type AnalyticsEmployeeStatsOut,
  type EmployeePeriod,
} from "@/lib/api/endpoints";
import { kRub, monthName, pctText, ratioText, toneClass } from "@/lib/analytics/format";
import { formatDate } from "@/lib/format/ru";
import { hours, num, rub } from "@/lib/production/format";
import { cn } from "@/lib/utils";

import { EmployeeDialog } from "./employee-dialog";

const PERIODS: { value: EmployeePeriod; label: string }[] = [
  { value: "4w", label: "4 недели" },
  { value: "m0", label: "текущий месяц" },
  { value: "m1", label: "прошлый месяц" },
];

type Mode = "h" | "rub";
type SortKey = keyof Pick<
  AnalyticsEmployeeStatsOut,
  | "worked"
  | "on_orders"
  | "earned"
  | "output_pct"
  | "use_pct"
  | "productivity_pct"
  | "defect_pct"
  | "rub"
  | "rub_per_hour"
  | "cost"
  | "return_ratio"
  | "contribution"
> | "name";

const HOUR_KEYS: SortKey[] = ["name", "worked", "on_orders", "earned", "output_pct", "use_pct", "productivity_pct", "defect_pct"];
const RUB_KEYS: SortKey[] = ["name", "worked", "earned", "rub", "rub_per_hour", "cost", "return_ratio", "contribution"];

/** Экран «Сотрудники» (`empPanel`/`empMoney` прототипа): выработка в нормо-часах и рублях. */
export function EmployeesView() {
  const [period, setPeriod] = useState<EmployeePeriod>("4w");
  const [department, setDepartment] = useState("");
  const [mode, setMode] = useState<Mode>("h");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "output_pct", desc: true });
  const [open, setOpen] = useState<string | null>(null);
  const query = useGetAnalyticsEmployees(
    { period, department_id: department || undefined },
    { query: { placeholderData: (prev) => prev } },
  );
  const data = query.data;

  const switchMode = (next: Mode) => {
    setMode(next);
    const allowed = next === "h" ? HOUR_KEYS : RUB_KEYS;
    if (!allowed.includes(sort.key)) setSort({ key: next === "h" ? "output_pct" : "rub", desc: true });
  };
  const rows = [...(data?.rows ?? [])].sort((a, b) => compare(a, b, sort.key) * (sort.desc ? -1 : 1));
  const header = (key: SortKey, label: string, title?: string) => (
    <TableHead
      className={cn("cursor-pointer select-none text-right", sort.key === key && "text-primary")}
      title={title}
      onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== "name" }))}
      aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : undefined}
    >
      {label}
      {sort.key === key ? (sort.desc ? " ▾" : " ▴") : ""}
    </TableHead>
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4 [&>*]:shrink-0">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Производительность по сотрудникам</h1>
        <OptionSelect
          ariaLabel="Период"
          className="w-40"
          value={period}
          onChange={(v) => setPeriod(v as EmployeePeriod)}
          options={PERIODS}
        />
        <OptionSelect
          ariaLabel="Подразделение"
          className="w-64"
          value={department}
          onChange={setDepartment}
          emptyLabel="Все участки"
          options={(data?.departments ?? []).map((d) => ({ value: d.id, label: d.name }))}
        />
        <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="Единицы">
          <Button size="sm" variant={mode === "h" ? "secondary" : "ghost"} onClick={() => switchMode("h")}>
            Нормо-часы
          </Button>
          <Button size="sm" variant={mode === "rub" ? "secondary" : "ghost"} onClick={() => switchMode("rub")}>
            В рублях
          </Button>
        </div>
        {data && (
          <span className="text-xs text-muted-foreground">
            {formatDate(data.date_from)}–{formatDate(data.date_to)}
          </span>
        )}
      </div>

      {data && mode === "h" && (
        <>
          <p className="-mt-2 text-xs text-muted-foreground">
            Источники: часы — табель (разноска по заказам и операциям), освоенные нормо-часы — закрытые объёмы операций,
            брак — записи контроля. Нормо-часы операции делятся между исполнителями{" "}
            <b>пропорционально их часам на этой операции</b>. Клик по строке — расшифровка.
          </p>
          <KpiRow>
            <Kpi value={`${hours(data.total.worked)} ч`} label="отработано" />
            <Kpi value={pctText(data.total.use_pct)} label="времени на заказах" />
            <Kpi value={`${hours(data.total.earned)} н-ч`} label="освоено" />
            <Kpi value={pctText(data.total.output_pct)} label="выработка на заказах" />
            <Kpi
              value={`${hours(data.unattributed)} н-ч`}
              label="не к кому отнести"
              tone={num(data.unattributed) > 5 ? "warn" : undefined}
              title="Освоено по операциям, на которые в табеле не разнесено ни одного часа"
            />
          </KpiRow>
        </>
      )}
      {data && mode === "rub" && (
        <>
          <p className="-mt-2 text-xs text-muted-foreground">
            Нормо-час оценён <b>по ставке участка</b> операции (плановая себестоимость). <b>Затраты на труд</b> —
            отработанные часы × ставка сотрудника × коэффициент кода (сверхурочные ×1,5, выходные ×2). <b>Отдача</b> —
            выработка ÷ затраты. Зарплату считает 1С:ЗУП, здесь — управленческая оценка.
          </p>
          <KpiRow>
            <Kpi value={`${kRub(data.total.rub)} ₽`} label="выработка за период" />
            <Kpi value={`${kRub(data.total.cost)} ₽`} label="затраты на труд" />
            <Kpi
              value={ratioText(data.total.return_ratio)}
              label="отдача, ₽ на ₽"
              tone={toneTone(data.total.return_ratio, 1, 0.85)}
            />
            <Kpi value={`${kRub(data.total.contribution)} ₽`} label="освоено сверх затрат" />
            <Kpi value={data.total.rub_per_hour === null ? "—" : rub(data.total.rub_per_hour)} label="на отработанный час" />
          </KpiRow>
        </>
      )}

      {data ? (
        <section className="overflow-x-auto rounded-lg border">
          <Table data-testid="employees-table">
            <TableHeader>
              <TableRow>
                <TableHead
                  className={cn("cursor-pointer select-none", sort.key === "name" && "text-primary")}
                  onClick={() => setSort((s) => ({ key: "name", desc: s.key === "name" ? !s.desc : false }))}
                >
                  Сотрудник
                </TableHead>
                <TableHead>Участок</TableHead>
                {mode === "h" ? (
                  <>
                    {header("worked", "Отработано, ч")}
                    {header("on_orders", "На заказах")}
                    <TableHead className="text-right">Накладные / простой</TableHead>
                    <TableHead className="text-right">Ремонт, ТО</TableHead>
                    <TableHead className="text-right">Сверхур.</TableHead>
                    <TableHead className="text-right">Отсут., дн</TableHead>
                    {header("earned", "Освоено, н-ч")}
                    {header("output_pct", "Выработка", "Освоено ÷ часы на заказах: скорость работы против нормы")}
                    {header("use_pct", "Использование", "Часы на заказах ÷ отработано")}
                    {header("productivity_pct", "Производительность", "Освоено ÷ отработано")}
                    {header("defect_pct", "Брак", "Доля брака на операциях сотрудника (по его часам)")}
                  </>
                ) : (
                  <>
                    {header("worked", "Отработано, ч")}
                    {header("earned", "Освоено, н-ч")}
                    {header("rub", "Выработка, ₽")}
                    {header("rub_per_hour", "₽ на час", "Выработка ÷ отработанные часы")}
                    {header("cost", "Затраты на труд, ₽")}
                    {header("return_ratio", "Отдача", "Выработка ÷ затраты на труд")}
                    {header("contribution", "Разница, ₽", "Выработка − затраты на труд")}
                  </>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow
                  key={r.employee_id}
                  className="cursor-pointer"
                  onClick={() => setOpen(r.employee_id)}
                  data-testid="employee-row"
                >
                  <TableCell>
                    <b>{r.full_name}</b>
                    <div className="text-xs text-muted-foreground">
                      {r.position}
                      {mode === "rub" && ` · ставка ${hours(r.hourly_rate)} ₽/ч`}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.work_center_short}</Badge>
                  </TableCell>
                  {mode === "h" ? <HourCells s={r.stats} /> : <RubCells s={r.stats} />}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">{query.isError ? "Не удалось загрузить данные." : "Загрузка…"}</p>
      )}

      {data && mode === "rub" && (
        <section className="overflow-x-auto rounded-lg border p-3">
          <h2 className="mb-2 font-semibold">Выработка по месяцам, тыс ₽</h2>
          <Table data-testid="employees-months">
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                {data.months.map((m) => (
                  <TableHead key={m} colSpan={2} className="text-center">
                    {monthName(m)}
                  </TableHead>
                ))}
                <TableHead className="text-right">Тренд</TableHead>
              </TableRow>
              <TableRow>
                <TableHead />
                {data.months.map((m) => (
                  <MonthSubHeads key={m} />
                ))}
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.employee_id} className="cursor-pointer" onClick={() => setOpen(r.employee_id)}>
                  <TableCell>{r.full_name}</TableCell>
                  {r.months.map((m) => (
                    <MonthCells key={m.month} rubValue={m.rub} ratio={m.return_ratio} />
                  ))}
                  <TableCell className="text-right">
                    <Trend row={r} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-2 text-xs text-muted-foreground">
            Тренд — прошлый месяц к позапрошлому (текущий месяц неполный). Ставки участков — из справочника участков,
            ставки сотрудников — из профилей табеля.
          </p>
        </section>
      )}

      <p className="text-xs text-muted-foreground">
        <b>Как читать.</b> Низкая выработка при высоком использовании — человек занят, но медленнее нормы (или норма
        занижена). Низкое использование — время уходит на накладные, ожидание, ремонты: это вопрос к организации, а не к
        работнику. Показатели — инструмент разбора с мастером, а не основание для взысканий.
      </p>

      <EmployeeDialog employeeId={open} period={period} onClose={() => setOpen(null)} />
    </div>
  );
}

function compare(a: AnalyticsEmployeeRowOut, b: AnalyticsEmployeeRowOut, key: SortKey): number {
  if (key === "name") return a.full_name.localeCompare(b.full_name, "ru");
  const va = a.stats[key];
  const vb = b.stats[key];
  // «—» (нет базы) — всегда ниже любого числа.
  return (va === null ? -Infinity : num(va)) - (vb === null ? -Infinity : num(vb)) || 0;
}

function toneTone(value: string | null, good: number, warn: number): "ok" | "warn" | "bad" | undefined {
  if (value === null) return undefined;
  const v = num(value);
  return v >= good ? "ok" : v >= warn ? "warn" : "bad";
}

function HourCells({ s }: { s: AnalyticsEmployeeStatsOut }) {
  const blank = (v: string) => (num(v) ? hours(v) : "");
  const defect = s.defect_pct === null ? null : num(s.defect_pct);
  return (
    <>
      <TableCell className="text-right tabular-nums">{hours(s.worked)}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(s.on_orders)}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(num(s.overhead) + num(s.idle))}</TableCell>
      <TableCell className="text-right tabular-nums">{blank(s.repair)}</TableCell>
      <TableCell className="text-right tabular-nums">{blank(s.overtime)}</TableCell>
      <TableCell className="text-right tabular-nums">{num(s.absent_days) ? Math.round(num(s.absent_days)) : ""}</TableCell>
      <TableCell className="text-right font-semibold tabular-nums">{hours(s.earned)}</TableCell>
      <TableCell className={cn("text-right font-semibold tabular-nums", toneClass(s.output_pct, 95, 80))}>
        {pctText(s.output_pct)}
      </TableCell>
      <TableCell className={cn("text-right tabular-nums", toneClass(s.use_pct, 80, 60))}>{pctText(s.use_pct)}</TableCell>
      <TableCell className={cn("text-right font-semibold tabular-nums", toneClass(s.productivity_pct, 85, 65))}>
        {pctText(s.productivity_pct)}
      </TableCell>
      <TableCell
        className={cn(
          "text-right tabular-nums",
          defect === null ? "" : defect > 4 ? "text-destructive" : defect > 2 ? "text-amber-700" : "text-emerald-700",
        )}
      >
        {defect === null ? "—" : `${defect.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`}
        {num(s.operator_defects) >= 0.5 && (
          <Badge variant="destructive" className="ml-1" title="Брак с причиной «Оператор»">
            опер. {hours(s.operator_defects)}
          </Badge>
        )}
      </TableCell>
    </>
  );
}

function RubCells({ s }: { s: AnalyticsEmployeeStatsOut }) {
  return (
    <>
      <TableCell className="text-right tabular-nums">{hours(s.worked)}</TableCell>
      <TableCell className="text-right tabular-nums">{hours(s.earned)}</TableCell>
      <TableCell className="text-right font-semibold tabular-nums">{rub(s.rub)}</TableCell>
      <TableCell className="text-right tabular-nums">{s.rub_per_hour === null ? "—" : rub(s.rub_per_hour)}</TableCell>
      <TableCell className="text-right tabular-nums">{rub(s.cost)}</TableCell>
      <TableCell className={cn("text-right font-semibold tabular-nums", toneClass(s.return_ratio, 1, 0.85))}>
        {ratioText(s.return_ratio)}
      </TableCell>
      <TableCell className={cn("text-right tabular-nums", num(s.contribution) < 0 && "text-destructive")}>
        {rub(s.contribution)}
      </TableCell>
    </>
  );
}

function MonthSubHeads() {
  return (
    <>
      <TableHead className="text-right text-xs font-normal">выработка</TableHead>
      <TableHead className="text-right text-xs font-normal">отдача</TableHead>
    </>
  );
}

function MonthCells({ rubValue, ratio }: { rubValue: string; ratio: string | null }) {
  return (
    <>
      <TableCell className="text-right font-semibold tabular-nums">
        {num(rubValue) ? Math.round(num(rubValue) / 1000).toLocaleString("ru-RU") : "—"}
      </TableCell>
      <TableCell className={cn("text-right tabular-nums", num(rubValue) ? toneClass(ratio, 1, 0.85) : "")}>
        {num(rubValue) ? ratioText(ratio) : "—"}
      </TableCell>
    </>
  );
}

function Trend({ row }: { row: AnalyticsEmployeeRowOut }) {
  const n = row.months.length;
  if (n < 3) return <>—</>;
  const before = num(row.months[n - 3].rub);
  const last = num(row.months[n - 2].rub);
  if (!before || !last) return <>—</>;
  const up = last >= before;
  return (
    <span className={up ? "text-emerald-700" : "text-destructive"}>
      {up ? "▲" : "▼"} {Math.abs(Math.round((last / before - 1) * 100))}%
    </span>
  );
}
