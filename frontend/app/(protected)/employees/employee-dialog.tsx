"use client";

import { HBarList } from "@/components/charts/hbar-list";
import { Kpi, KpiRow } from "@/components/charts/kpi";
import { StackChart } from "@/components/charts/stack-chart";
import { useCards } from "@/components/production/card-host";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGetAnalyticsEmployee, type EmployeePeriod } from "@/lib/api/endpoints";
import { dayMonth, kRub, pctText, ratioText } from "@/lib/analytics/format";
import { formatDate } from "@/lib/format/ru";
import { hours, num } from "@/lib/production/format";
import { cn } from "@/lib/utils";

/** Карточка сотрудника (`empDialog` прототипа): структура времени, недели, операции. */
export function EmployeeDialog({
  employeeId,
  period,
  onClose,
}: {
  employeeId: string | null;
  period: EmployeePeriod;
  onClose: () => void;
}) {
  return (
    <Dialog open={employeeId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        {employeeId && <Card employeeId={employeeId} period={period} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function Card({ employeeId, period, onClose }: { employeeId: string; period: EmployeePeriod; onClose: () => void }) {
  const cards = useCards();
  const query = useGetAnalyticsEmployee(employeeId, { period });
  const card = query.data;
  if (!card) {
    return (
      <DialogHeader>
        <DialogTitle>Сотрудник</DialogTitle>
        <DialogDescription>{query.isError ? "Не удалось загрузить карточку." : "Загрузка…"}</DialogDescription>
      </DialogHeader>
    );
  }
  const s = card.stats;
  const worked = num(s.worked);
  const structure = [
    { label: "На заказах", value: num(s.on_orders), color: "#2f5bd3" },
    { label: "Накладные", value: num(s.overhead), color: "#b4bac4" },
    { label: "Простой", value: num(s.idle), color: "#e9a23b" },
    { label: "Ремонт и ТО", value: num(s.repair), color: "#c2410c" },
    { label: "Обучение", value: num(s.training), color: "#8fd1a8" },
  ].filter((r) => r.value > 0);

  return (
    <div className="flex flex-col gap-4" data-testid="employee-card">
      <DialogHeader>
        <DialogTitle>{card.full_name}</DialogTitle>
        <DialogDescription>
          {card.position} · {card.department_name} · {card.work_center_short} · ставка {hours(card.hourly_rate)} ₽/ч ·{" "}
          {formatDate(card.date_from)}–{formatDate(card.date_to)}
        </DialogDescription>
      </DialogHeader>
      <KpiRow>
        <Kpi value={`${hours(s.worked)} ч`} label="отработано" />
        <Kpi value={`${hours(s.earned)} н-ч`} label="освоено" />
        <Kpi value={`${kRub(s.rub)} ₽`} label="выработка по ставке участка" />
        <Kpi value={ratioText(s.return_ratio)} label="отдача на ₽ труда" />
        <Kpi value={pctText(s.output_pct)} label="выработка" />
        <Kpi value={pctText(s.use_pct)} label="использование" />
        <Kpi value={pctText(s.productivity_pct)} label="производительность" />
      </KpiRow>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <h3 className="font-semibold">Структура времени</h3>
          <HBarList
            rows={structure.map((r) => ({
              ...r,
              label: `${r.label} · ${worked ? Math.round((r.value / worked) * 100) : 0}%`,
            }))}
          />
          {num(s.overtime) > 0 && <p className="text-xs text-muted-foreground">Из них сверхурочно {hours(s.overtime)} ч.</p>}
          {num(s.absent_days) > 0 && (
            <p className="text-xs text-muted-foreground">Отсутствия: {hours(s.absent_days)} дн.</p>
          )}
          <h3 className="font-semibold">По неделям: часы и освоено</h3>
          {card.weeks.length ? (
            <StackChart
              width={520}
              height={180}
              categories={card.weeks.map((w) => dayMonth(w.week_start))}
              series={[
                { name: "Освоено, н-ч", color: "#2f5bd3", values: card.weeks.map((w) => num(w.earned)) },
                {
                  name: "Отработано сверх освоенного, ч",
                  color: "#c9d4ee",
                  values: card.weeks.map((w) => Math.max(0, num(w.hours) - num(w.earned))),
                },
              ]}
              topLabels={card.weeks.map((w) => pctText(w.productivity_pct))}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Нет часов за период.</p>
          )}
          <p className="text-xs text-muted-foreground">Над столбцом — производительность недели (освоено ÷ отработано).</p>
        </div>
        <div className="flex flex-col gap-3">
          <h3 className="font-semibold">Операции</h3>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Заказ · операция</TableHead>
                  <TableHead className="text-right">Его часы</TableHead>
                  <TableHead className="text-right">Освоено</TableHead>
                  <TableHead className="text-right">₽</TableHead>
                  <TableHead className="text-right">Выработка</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {card.operations.length ? (
                  card.operations.map((op) => (
                    <TableRow key={op.operation_id}>
                      <TableCell className="whitespace-normal">
                        <button
                          type="button"
                          className="text-left text-primary hover:underline"
                          onClick={() => {
                            onClose();
                            cards.openOperation(op.operation_id);
                          }}
                        >
                          {op.order_number} · {op.operation_name}
                        </button>
                        <div className="text-xs text-muted-foreground">
                          норма {hours(op.norm_hours)} н-ч на операцию · {op.status === "done" ? "закрыта" : "в работе"}
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{hours(op.hours)}</TableCell>
                      <TableCell className="text-right tabular-nums">{hours(op.earned)}</TableCell>
                      <TableCell className="text-right tabular-nums">{kRub(op.rub)}</TableCell>
                      <TableCell
                        className={cn(
                          "text-right tabular-nums",
                          op.output_pct !== null && num(op.output_pct) < 80 && "text-destructive",
                        )}
                      >
                        {pctText(op.output_pct)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground">
                      Нет часов на операциях
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          {num(s.checked) > 0 && (
            <>
              <h3 className="font-semibold">Качество</h3>
              <p className="text-sm">
                На его операциях проверено ~{Math.round(num(s.checked))}, брак ~{hours(s.defects)} (
                {num(s.defect_pct).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%)
                {num(s.operator_defects) >= 0.5 && `, из них по причине «Оператор» ~${hours(s.operator_defects)}`}.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
