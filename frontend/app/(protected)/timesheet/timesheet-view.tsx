"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import {
  approveTimesheet,
  closeTimesheet,
  confirmTimesheetHours,
  fillTimesheetFromPlan,
  reopenTimesheet,
  returnTimesheet,
  sendTimesheet,
  submitTimesheet,
  useGetTimesheetGrid,
  useGetTimesheetReview,
  useListTimesheetDepartments,
} from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

import { DayDialog } from "./day-dialog";
import { PERIOD_STATUS_LABELS, PERIOD_STATUS_TONE, hours, monthTitle, recentMonths } from "./labels";
import { ChecksPanel, SummaryPanel } from "./period-panels";
import { ReasonDialog } from "./reason-dialog";
import { TimesheetGrid } from "./timesheet-grid";

const MONTHS = recentMonths(5);

/** Все запросы табеля — по префиксу пути: после действия сетка, согласование и
 * статусы в выборе подразделения перечитываются вместе. */
export function useInvalidateTimesheet(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/api/v1/timesheet"),
    });
}

type ReasonAction = "return" | "reopen";

export function TimesheetView() {
  const [month, setMonth] = useState(MONTHS[1]);
  const [chosenDepartment, setChosenDepartment] = useState<string | null>(null);
  const [expand, setExpand] = useState(false);
  const [openDay, setOpenDay] = useState<{ employeeId: string; day: string } | null>(null);
  const [reasonAction, setReasonAction] = useState<ReasonAction | null>(null);
  const invalidate = useInvalidateTimesheet();

  const departments = useListTimesheetDepartments({ month });
  const departmentId = chosenDepartment ?? departments.data?.[0]?.department_id ?? "";
  const grid = useGetTimesheetGrid(departmentId, month, { query: { enabled: Boolean(departmentId) } });
  const review = useGetTimesheetReview(departmentId, month, { query: { enabled: Boolean(departmentId) } });

  const action = useMutation({
    mutationFn: async ({ run }: { run: () => Promise<unknown>; done: string }) => run(),
    onSuccess: async (_data, { done }) => {
      toast.success(done);
      await invalidate();
    },
  });

  const period = grid.data?.period;
  const abilities = period?.abilities;
  const blocking = grid.data?.checks.filter((c) => c.is_blocking) ?? [];
  const run = (fn: () => Promise<unknown>, done: string) => action.mutate({ run: fn, done });

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Табель</h1>
        <NativeSelect
          aria-label="Месяц"
          className="w-40"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        >
          {MONTHS.map((m) => (
            <option key={m} value={m}>
              {monthTitle(m)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Подразделение"
          className="w-96"
          value={departmentId}
          onChange={(e) => setChosenDepartment(e.target.value)}
        >
          {departments.data?.map((d) => (
            <option key={d.department_id} value={d.department_id}>
              {d.name} — {PERIOD_STATUS_LABELS[d.status]}
            </option>
          ))}
        </NativeSelect>
        {period && (
          <span
            className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", PERIOD_STATUS_TONE[period.status])}
            data-testid="period-status"
          >
            {PERIOD_STATUS_LABELS[period.status]}
            {period.version > 1 ? ` · версия ${period.version}` : ""}
          </span>
        )}
        {grid.data && (
          <span className="text-xs text-muted-foreground">
            норма {hours(grid.data.norm_hours)} ч
            {grid.data.head_name ? ` · руководитель ${grid.data.head_name}` : ""}
          </span>
        )}
        <span className="flex-1" />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={expand} onChange={(e) => setExpand(e.target.checked)} />
          показать разноску по объектам
        </label>
      </div>

      {abilities && (
        <div className="flex flex-wrap items-center gap-2">
          {abilities.can_fill_plan && (
            <Button
              variant="outline"
              size="sm"
              disabled={action.isPending}
              title="Незакрытые рабочие дни до вчера — по плану операций участков"
              onClick={() =>
                run(async () => {
                  const r = await fillTimesheetFromPlan(departmentId, month);
                  if (r.filled_days === 0) toast.info("Незакрытых дней нет");
                }, "Табель заполнен по плану")
              }
            >
              Заполнить по плану
            </Button>
          )}
          {abilities.can_edit && (
            <Button
              size="sm"
              disabled={action.isPending || !abilities.can_submit}
              title={abilities.can_submit ? undefined : "Есть блокирующие замечания"}
              onClick={() => run(() => submitTimesheet(departmentId, month), "Табель подан на согласование")}
            >
              Подать на согласование
            </Button>
          )}
          {abilities.can_confirm_manager && (
            <Button
              size="sm"
              disabled={action.isPending}
              onClick={() => run(() => confirmTimesheetHours(departmentId, month), "Часы по вашим заказам подтверждены")}
            >
              Подтвердить часы по моим заказам
            </Button>
          )}
          {abilities.can_return && (
            <Button
              size="sm"
              disabled={action.isPending || !abilities.can_approve}
              title={abilities.can_approve ? undefined : "Ждём подтверждения руководителей проектов"}
              onClick={() => run(() => approveTimesheet(departmentId, month), "Табель утверждён")}
            >
              Утвердить период
            </Button>
          )}
          {abilities.can_return && (
            <Button variant="outline" size="sm" disabled={action.isPending} onClick={() => setReasonAction("return")}>
              Вернуть на доработку
            </Button>
          )}
          {abilities.can_send && (
            <Button
              size="sm"
              disabled={action.isPending}
              onClick={() => run(() => sendTimesheet(departmentId, month), "Табель передан в 1С")}
            >
              Передать в 1С
            </Button>
          )}
          {abilities.can_close && (
            <Button
              size="sm"
              disabled={action.isPending}
              onClick={() => run(() => closeTimesheet(departmentId, month), "Период закрыт")}
            >
              Получить начисления и закрыть
            </Button>
          )}
          {abilities.can_reopen && (
            <Button variant="outline" size="sm" disabled={action.isPending} onClick={() => setReasonAction("reopen")}>
              Открыть для корректировки
            </Button>
          )}
          {!Object.values(abilities).some(Boolean) && (
            <span className="text-xs text-muted-foreground">Действий с периодом у вас нет — только просмотр.</span>
          )}
        </div>
      )}

      <p className="rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
        Первичный ввод — <b>разноска</b>: сотрудник, день, вид времени, заказ или операция, часы. Табель по видам
        времени строится из неё автоматически. Клик по ячейке — разноска дня.
      </p>

      {grid.isLoading && <p className="text-sm text-muted-foreground">Загрузка табеля…</p>}
      {grid.data && (
        <>
          <TimesheetGrid
            grid={grid.data}
            expand={expand}
            onCellClick={(employeeId, day) => setOpenDay({ employeeId, day })}
          />
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <Legend className="bg-red-100" text="не закрыт" />
            <Legend className="bg-amber-50" text="есть часы на накладные или простой" />
            <Legend className="bg-blue-50" text="отпуск, больничный" />
            <Legend className="bg-emerald-50" text="командировка" />
            <span>
              <sup>+2</sup> сверхурочные
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChecksPanel checks={grid.data.checks} blocking={blocking.length} review={review.data} />
            <SummaryPanel grid={grid.data} review={review.data} departmentId={departmentId} month={month} />
          </div>
        </>
      )}

      {openDay && (
        <DayDialog
          employeeId={openDay.employeeId}
          day={openDay.day}
          onClose={() => setOpenDay(null)}
          onSaved={invalidate}
        />
      )}
      <ReasonDialog
        open={reasonAction !== null}
        title={reasonAction === "return" ? "Вернуть на доработку" : "Открыть период для корректировки?"}
        description={
          reasonAction === "reopen"
            ? "Версия увеличится, после правок период пройдёт согласование и уйдёт в 1С целиком заново."
            : "Укажите, что исправить."
        }
        confirmLabel={reasonAction === "return" ? "Вернуть" : "Открыть"}
        onClose={() => setReasonAction(null)}
        onConfirm={async (comment) => {
          const fn =
            reasonAction === "return"
              ? () => returnTimesheet(departmentId, month, { comment })
              : () => reopenTimesheet(departmentId, month, { comment });
          await action.mutateAsync({
            run: fn,
            done: reasonAction === "return" ? "Табель возвращён на доработку" : "Период открыт для корректировки",
          });
          setReasonAction(null);
        }}
      />
    </div>
  );
}

function Legend({ className, text }: { className: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i className={cn("inline-block size-3 rounded-sm border", className)} />
      {text}
    </span>
  );
}
