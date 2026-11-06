"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  annulProductionOrderDocument,
  approveProductionOperation,
  approveProductionOrderDocument,
  addProductionComment,
  moveProductionOperation,
  replanProductionOrder,
  setProductionOperationPredecessors,
  setProductionOperationProgress,
  setProductionOperationStatus,
  setProductionStageResponsible,
  updateProductionOperation,
  updateProductionOrder,
  uploadProductionOrderDocument,
  useGetInquiry,
  useGetProductionOrderSchedule,
  useListDocumentKinds,
  useListProductionEmployees,
  useListProductionJournal,
  useListProductionOrderDocuments,
  type JournalKind,
  type OperationRowOut,
  type OperationStatus,
  type OrderOut,
  type ScheduleOut,
} from "@/lib/api/endpoints";
import { fd, fdl, todayIso } from "@/lib/production/dates";
import { hours, num, rub } from "@/lib/production/format";
import { JOURNAL_KIND_LABELS, OPERATION_STATUS_LABELS, PHASE_LABELS, stageTitle } from "@/lib/production/stages";
import { useAction } from "@/lib/production/use-action";
import { formatDateTime } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import {
  CellInput,
  CellSelect,
  Field,
  Line,
  NativeSelect,
  Note,
  Pill,
  ProgressBar,
  SectionTitle,
  TABLE,
  TextArea,
  TextInput,
  Visa,
} from "./bits";
import { useCards } from "./card-host";
import { CommentButton } from "./comment-button";
import { GanttChart, type GanttRow } from "./gantt-chart";
import { CalcTables } from "./inquiry-tabs";
import { TextDialog } from "./stage-dialogs";

function useEmployees() {
  return useListProductionEmployees({ query: { staleTime: 5 * 60_000 } }).data ?? [];
}

// --- Основное --------------------------------------------------------------------

export function OrderMainTab({ order }: { order: OrderOut }) {
  const { run } = useAction();
  const employees = useEmployees();
  const canEdit = order.order_abilities.can_edit;

  return (
    <>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Заказчик">
          <TextInput value={order.customer_name} disabled />
        </Field>
        <Field label="Объект">
          <TextInput value={order.object_name} disabled />
        </Field>
        <Field label="Изделие">
          <TextInput value={order.product_name} disabled />
        </Field>
        <Field label="Количество, шт.">
          <TextInput value={Number(order.quantity)} disabled />
        </Field>
        <Field label="Срок по договору">
          <TextInput
            type="date"
            name="order-due"
            defaultValue={order.due_date}
            key={order.due_date}
            disabled={!canEdit}
            onBlur={(e) => {
              if (e.target.value && e.target.value !== order.due_date)
                void run(() => updateProductionOrder(order.id, { due_date: e.target.value, manager_id: order.manager_id }), "Срок изменён");
            }}
          />
        </Field>
        <Field label="Менеджер проекта">
          <NativeSelect
            value={order.manager_id}
            disabled={!canEdit}
            onChange={(e) =>
              void run(() => updateProductionOrder(order.id, { due_date: order.due_date, manager_id: e.target.value }), "Менеджер изменён")
            }
          >
            {!employees.some((e) => e.id === order.manager_id) ? <option value={order.manager_id}>{order.manager_name}</option> : null}
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.full_name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Дата запуска">
          <TextInput value={fdl(order.planned_start)} disabled />
        </Field>
        <Field label="Создан">
          <TextInput value={formatDateTime(order.created_at)} disabled />
        </Field>
      </div>
      <div className="mt-4 grid grid-cols-[1fr_290px] gap-5">
        <div>
          <SectionTitle>Ответственные и визы по этапам</SectionTitle>
          <table className={TABLE}>
            <thead>
              <tr>
                <th>Этап</th>
                <th>Ответственный</th>
                <th>Виза</th>
              </tr>
            </thead>
            <tbody>
              {order.approvals.map((a) => (
                <tr key={a.stage} className={cn(a.stage === order.stage && "bg-blue-50")}>
                  <td>{a.stage_label}</td>
                  <td>
                    <CellSelect
                      value={a.responsible_id ?? ""}
                      disabled={!canEdit || !!a.approved_at}
                      onChange={(e) =>
                        void run(
                          () => setProductionStageResponsible(order.id, a.stage, { responsible_id: e.target.value }),
                          "Ответственный назначен",
                        )
                      }
                    >
                      <option value="">—</option>
                      {!employees.some((e) => e.id === a.responsible_id) && a.responsible_id ? (
                        <option value={a.responsible_id}>{a.responsible_name}</option>
                      ) : null}
                      {employees.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.full_name}
                        </option>
                      ))}
                    </CellSelect>
                  </td>
                  <td>
                    {a.approved_at ? (
                      <Visa>
                        {a.approved_by_name} · {formatDateTime(a.approved_at)}
                        {a.comment ? ` · ${a.comment}` : ""}
                      </Visa>
                    ) : (
                      <span className="text-xs text-muted-foreground">нет</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {order.derived_stage !== order.stage ? (
            <Note>
              По состоянию операций заказ можно переводить на этап «{stageTitle(order.derived_stage)}».
            </Note>
          ) : null}
        </div>
        <div className="rounded-xl border px-3.5 py-2.5 text-[13px]">
          <Line label="Трудоёмкость" value={`${hours(order.hours_total)} н-ч`} />
          <Line label="Освоено" value={`${hours(order.earned_total)} н-ч`} />
          <Line label="Готовность" value={`${Math.round(num(order.progress))}%`} />
          <Line label="Начало" value={fdl(order.planned_start)} />
          <Line label="Окончание" value={fdl(order.planned_finish)} />
          <Line label="Срок" value={fdl(order.due_date)} />
          <Line label="Труд план" value={rub(order.labor_cost_planned)} />
          <Line label="Цена с НДС" value={rub(order.contract_total)} big />
        </div>
      </div>
    </>
  );
}

// --- Калькуляция (только чтение) -------------------------------------------------

export function OrderCalcTab({ order }: { order: OrderOut }) {
  const inquiry = useGetInquiry(order.inquiry_id ?? "", { query: { enabled: !!order.inquiry_id } });
  if (!order.inquiry_id) return <Note>Заказ создан не из заявки — калькуляции нет.</Note>;
  if (!inquiry.data) return <p className="text-sm text-muted-foreground">Загрузка калькуляции…</p>;
  return (
    <>
      <Note>Заказ запущен — калькуляция зафиксирована (заявка {order.inquiry_number}).</Note>
      <CalcTables inquiry={inquiry.data} readOnly />
    </>
  );
}

// --- План ------------------------------------------------------------------------

export function scheduleToGantt(order: OrderOut, schedule: ScheduleOut): GanttRow {
  return {
    id: order.id,
    number: order.number,
    customer_name: order.customer_name,
    product_name: order.product_name,
    stage: order.stage,
    due_date: order.due_date,
    planned_start: schedule.planned_start,
    planned_finish: schedule.planned_finish,
    health: order.health,
    can_plan: order.order_abilities.can_plan,
    operations: schedule.operations,
  };
}

export function OrderPlanTab({ order }: { order: OrderOut }) {
  const { run } = useAction();
  const cards = useCards();
  const employees = useEmployees();
  const schedule = useGetProductionOrderSchedule(order.id);
  const [start, setStart] = useState(order.planned_start);
  useEffect(() => setStart(order.planned_start), [order.planned_start]);

  const data = schedule.data;
  const ops = useMemo(() => data?.operations ?? [], [data]);
  const numberOf = useMemo(() => new Map(ops.map((o, i) => [o.id, i + 1])), [ops]);
  const byId = useMemo(() => new Map(ops.map((o) => [o.id, o])), [ops]);
  if (!data) return <p className="text-sm text-muted-foreground">Загрузка плана…</p>;

  const late = data.planned_finish && data.planned_finish > order.due_date;
  const canPlan = order.order_abilities.can_plan;

  function savePredecessors(op: OperationRowOut, value: string) {
    const numbers = value.split(/[,;\s]+/).filter(Boolean).map(Number);
    const current = op.predecessor_ids.map((id) => numberOf.get(id)).sort((a, b) => a! - b!).join(", ");
    if (numbers.sort((a, b) => a - b).join(", ") === current) return;
    if (numbers.some((n) => !Number.isInteger(n) || n < 1 || n > ops.length || ops[n - 1].id === op.id)) {
      toast.error("Неверный номер операции в предшественниках.");
      return;
    }
    void run(
      () => setProductionOperationPredecessors(op.id, { predecessor_ids: numbers.map((n) => ops[n - 1].id) }),
      "Связи сохранены",
    );
  }

  return (
    <>
      <Note>
        Колонка <b>«Предш.»</b> — номера операций, после окончания которых начинается эта (через запятую). Длительность =
        н-ч ÷ (8 ч × исполнителей), для снабжения — срок поставки; всё в рабочих днях. <b>«Не ранее»</b> — ограничение даты
        начала. Начатые операции стоят по факту.
      </Note>
      <div className="flex flex-wrap items-end gap-2.5">
        <Field label="Начало работ" className="w-40">
          <TextInput type="date" value={start} disabled={!canPlan} onChange={(e) => setStart(e.target.value)} />
        </Field>
        {canPlan ? (
          <Button variant="outline" onClick={() => void run(() => replanProductionOrder(order.id, { planned_start: start }), "План пересчитан")}>
            Пересчитать план
          </Button>
        ) : null}
        <span className="flex-1" />
        <span className="text-sm">
          Окончание <b>{fdl(data.planned_finish)}</b> · {data.length} раб. дн. · срок {fdl(order.due_date)}{" "}
          <Pill tone={late ? "r" : "g"}>{late ? "позже срока" : "в срок"}</Pill>
        </span>
      </div>
      {data.critical_path.length ? (
        <Note tone="crit">
          <b>Критический путь ({data.length} раб. дн.):</b>{" "}
          {data.critical_path.map((id) => `${numberOf.get(id)}. ${byId.get(id)?.name ?? ""}`).join(" → ")}
          <br />
          Задержка любой из этих операций сдвигает срок заказа. У остальных есть резерв — колонка «Резерв».
        </Note>
      ) : null}
      {data.has_violations ? (
        <Note tone="bad">Есть нарушения связей (операция начата раньше окончания предшественника) — отмечены в таблице.</Note>
      ) : null}
      <table className={cn(TABLE, "mt-3")} data-testid="plan-table">
        <thead>
          <tr>
            <th className="w-9">№</th>
            <th>Операция</th>
            <th>Уч.</th>
            <th className="text-right">Н-ч/дн</th>
            <th className="w-14 text-right">Исп.</th>
            <th className="text-right">Дл.</th>
            <th className="w-20">Предш.</th>
            <th className="w-32">Не ранее</th>
            <th>Начало</th>
            <th>Оконч.</th>
            <th className="text-right">Резерв</th>
            <th className="w-40">Ответственный</th>
          </tr>
        </thead>
        <tbody>
          {ops.map((op, i) => {
            const edit = op.abilities.can_edit_plan;
            return (
              <tr key={op.id} className={cn(op.is_critical && "bg-orange-50 [&>td:first-child]:shadow-[inset_3px_0_0_#c2410c]")}>
                <td className="text-muted-foreground">{i + 1}</td>
                <td>
                  <button type="button" className="text-left text-blue-700 hover:underline" onClick={() => cards.openOperation(op.id)}>
                    {op.name}
                  </button>
                  {op.status === "done" ? <Visa>{""}</Visa> : null}
                  {op.violates_dependency ? <Pill tone="r" className="ml-1">связь</Pill> : null}
                </td>
                <td title={op.work_center_name}>
                  <Pill tone={op.is_supply ? "y" : "n"}>{op.work_center_short_name}</Pill>
                </td>
                <td className="text-right tabular-nums">{hours(op.hours)}</td>
                <td>
                  {op.is_supply ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <CellInput
                      type="number"
                      min={1}
                      max={op.capacity}
                      className="text-right"
                      defaultValue={op.people}
                      key={`p${op.people}`}
                      disabled={!edit}
                      onBlur={(e) => {
                        const v = Math.min(op.capacity, Math.max(1, Number(e.target.value) || 1));
                        if (v !== op.people) void run(() => updateProductionOperation(op.id, { people: v }), "Исполнители изменены");
                      }}
                    />
                  )}
                </td>
                <td className="text-right">{op.duration}</td>
                <td>
                  <CellInput
                    placeholder="—"
                    defaultValue={op.predecessor_ids.map((id) => numberOf.get(id)).sort((a, b) => a! - b!).join(", ")}
                    key={`d${op.predecessor_ids.join()}`}
                    disabled={!edit}
                    onBlur={(e) => savePredecessors(op, e.target.value)}
                  />
                </td>
                <td>
                  <CellInput
                    type="date"
                    defaultValue={op.not_before ?? ""}
                    key={`n${op.not_before}`}
                    disabled={!edit}
                    onBlur={(e) => {
                      const v = e.target.value || null;
                      if (v !== op.not_before)
                        void run(() => updateProductionOperation(op.id, { not_before: v }), v ? "Ограничение «не ранее» задано" : "Ограничение снято");
                    }}
                  />
                </td>
                <td>{fd(op.planned_start)}</td>
                <td>{fd(op.planned_finish)}</td>
                <td className="text-right">
                  {op.slack == null ? "—" : op.slack <= 0 ? <b className="text-orange-700">0</b> : `${op.slack} дн.`}
                </td>
                <td>
                  <ResponsibleSelect op={op} employees={employees} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <SectionTitle>Сетевой график</SectionTitle>
      <GanttChart
        rows={[scheduleToGantt(order, data)]}
        mini
        onOpenOperation={(id) => cards.openOperation(id)}
        onMoveOperation={(op, day) => void run(() => moveProductionOperation(op.id, { start: day }), `Перенесена на ${fd(day)}`)}
      />
    </>
  );
}

function ResponsibleSelect({ op, employees }: { op: OperationRowOut; employees: { id: string; full_name: string }[] }) {
  const { run } = useAction();
  return (
    <CellSelect
      value={op.responsible_id ?? ""}
      disabled={!op.abilities.can_set_responsible}
      onChange={(e) => {
        if (e.target.value)
          void run(() => updateProductionOperation(op.id, { responsible_id: e.target.value }), "Ответственный назначен");
      }}
    >
      <option value="">—</option>
      {op.responsible_id && !employees.some((e) => e.id === op.responsible_id) ? (
        <option value={op.responsible_id}>{op.responsible_name}</option>
      ) : null}
      {employees.map((e) => (
        <option key={e.id} value={e.id}>
          {e.full_name}
        </option>
      ))}
    </CellSelect>
  );
}

// --- Состояние -------------------------------------------------------------------

export function OperationVisaButton({ op, onDone, size = "xs" }: { op: OperationRowOut; onDone?: () => void; size?: "xs" | "sm" }) {
  const { run } = useAction();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        size={size}
        className="bg-emerald-700 hover:bg-emerald-700/90"
        disabled={!op.abilities.can_approve}
        title={op.abilities.can_approve ? "" : `Визу ставит ${op.responsible_name || "ответственный"}`}
        onClick={() => setOpen(true)}
      >
        Виза
      </Button>
      <TextDialog
        open={open}
        title={`Виза: «${op.name}»`}
        description="Операция будет отмечена выполненной."
        label="Комментарий"
        placeholder="Например: изготовлено 20 шт., отклонений нет"
        okText="Поставить визу"
        onOpenChange={setOpen}
        onSubmit={async (comment) => {
          const ok = await run(() => approveProductionOperation(op.id, { comment }), "Операция завизирована");
          if (ok) onDone?.();
        }}
      />
    </>
  );
}

export function StatusSelect({ op }: { op: OperationRowOut }) {
  const { run } = useAction();
  if (op.status === "done") return <Visa>{op.approved_by_name}</Visa>;
  return (
    <CellSelect
      value={op.status}
      disabled={!op.abilities.can_change_status}
      data-testid="op-status"
      onChange={(e) =>
        void run(
          () => setProductionOperationStatus(op.id, { status: e.target.value as OperationStatus }),
          `Статус: ${OPERATION_STATUS_LABELS[e.target.value as OperationStatus]}`,
        )
      }
    >
      {(["wait", "work", "check"] as const).map((s) => (
        <option key={s} value={s}>
          {OPERATION_STATUS_LABELS[s]}
        </option>
      ))}
    </CellSelect>
  );
}

export function ProgressSlider({ op }: { op: OperationRowOut }) {
  const { run } = useAction();
  const [value, setValue] = useState(op.status === "done" ? 100 : op.progress);
  useEffect(() => setValue(op.status === "done" ? 100 : op.progress), [op.progress, op.status]);
  const commit = (v: number) => {
    if (v !== op.progress)
      void run(
        () => setProductionOperationProgress(op.id, { progress: v }),
        v === 100 ? `Выполнено 100%, передано на визу ${op.responsible_name}` : `Выполнено ${v}%`,
      );
  };
  return (
    <div className="flex items-center gap-1.5">
      <input
        type="range"
        min={0}
        max={100}
        step={10}
        value={value}
        disabled={!op.abilities.can_set_progress}
        className="w-full accent-blue-600"
        aria-label="Выполнено"
        onChange={(e) => setValue(Number(e.target.value))}
        onPointerUp={(e) => commit(Number((e.target as HTMLInputElement).value))}
        onKeyUp={(e) => commit(Number((e.target as HTMLInputElement).value))}
      />
      <span className="w-9 text-right tabular-nums">{value}%</span>
    </div>
  );
}

export function OrderStateTab({ order }: { order: OrderOut }) {
  const cards = useCards();
  const employees = useEmployees();
  const schedule = useGetProductionOrderSchedule(order.id);
  if (order.stage === "launch") {
    return (
      <Note>
        Ход выполнения ведётся после запуска заказа: с этапа «Подготовка производства». Сейчас: <b>{stageTitle(order.stage)}</b>.
      </Note>
    );
  }
  const ops = schedule.data?.operations ?? [];
  const today = todayIso();
  const byId = new Map(ops.map((o) => [o.id, o]));
  const progress = Math.round(num(order.progress));

  return (
    <>
      <div className="grid grid-cols-[1fr_290px] gap-5">
        <div>
          <div className="flex items-center gap-2.5">
            <b className="text-[26px]">{progress}%</b>
            <span className="text-xs text-muted-foreground">готовность по трудоёмкости</span>
            <Pill tone={order.health.color} className="ml-auto">
              {order.health.text}
            </Pill>
          </div>
          <ProgressBar value={progress} className="h-2" />
          <Note>
            Операцию закрывает <b>виза ответственного</b> — только после закрытия всех предшественников. Исполнитель ставит
            100% → статус «На визе».
          </Note>
        </div>
        <div className="rounded-xl border px-3.5 py-2.5 text-[13px]">
          <Line label="Запуск" value={fdl(order.planned_start)} />
          <Line label="План окончания" value={fdl(order.planned_finish)} />
          <Line label="Срок по договору" value={fdl(order.due_date)} />
          <Line label="Освоено / план" value={`${hours(order.earned_total)} / ${hours(order.hours_total)} н-ч`} />
          <Line label="Операций выполнено" value={`${order.operations_done} из ${order.operations_total}`} />
        </div>
      </div>
      <table className={cn(TABLE, "mt-3")} data-testid="state-table">
        <thead>
          <tr>
            <th>Операция</th>
            <th>План</th>
            <th className="w-40">Ответственный</th>
            <th className="w-32">Статус</th>
            <th className="w-44">Выполнено</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(["prep", "prod", "qc"] as const).map((phase) => {
            const list = ops.filter((o) => o.phase === phase);
            if (!list.length) return null;
            return [
              <tr key={phase}>
                <td colSpan={6} className="bg-slate-50 pt-2.5 text-xs font-semibold text-muted-foreground">
                  {PHASE_LABELS[phase]}
                </td>
              </tr>,
              ...list.map((op) => {
                const waiting = op.predecessor_ids.map((id) => byId.get(id)).filter((p) => p && p.status !== "done");
                const late = op.status !== "done" && !!op.planned_finish && op.planned_finish < today;
                return (
                  <tr key={op.id} className={cn(op.is_critical && "bg-orange-50")}>
                    <td>
                      <button type="button" className="text-left text-blue-700 hover:underline" onClick={() => cards.openOperation(op.id)}>
                        {op.name}
                      </button>
                      {op.requires_inspection ? (
                        <Pill tone="n" className="ml-1" title="Есть точка контроля">
                          контроль
                        </Pill>
                      ) : null}
                      <div className="text-xs text-muted-foreground">
                        {op.work_center_name}
                        {waiting.length && op.status !== "done" ? ` · ждёт: ${waiting.map((p) => p!.name).join(", ")}` : ""}
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      {fd(op.planned_start)}–{fd(op.planned_finish)}
                      {late ? <Pill tone="r" className="ml-1">отставание</Pill> : null}
                    </td>
                    <td>
                      <ResponsibleSelect op={op} employees={employees} />
                    </td>
                    <td>
                      <StatusSelect op={op} />
                    </td>
                    <td>
                      {op.is_supply ? (
                        <span className="text-xs text-muted-foreground">
                          {op.status === "done" ? "поставлено" : `поставка ${hours(op.hours)} дн.`}
                        </span>
                      ) : (
                        <ProgressSlider op={op} />
                      )}
                    </td>
                    <td className="whitespace-nowrap">
                      {op.status !== "done" ? <OperationVisaButton op={op} /> : null}{" "}
                      {order.order_abilities.can_comment ? (
                        <CommentButton orderId={order.id} operationId={op.id} label="💬" title={`Комментарий: «${op.name}»`} />
                      ) : null}
                    </td>
                  </tr>
                );
              }),
            ];
          })}
        </tbody>
      </table>
    </>
  );
}

// --- Документы -------------------------------------------------------------------

const EXT_KIND: [string[], string][] = [
  [["nc", "tap", "mpf", "ngc", "iso", "h", "cnc"], "production.cnc"],
  [["dwg", "dxf", "step", "stp", "igs", "iges", "sldprt", "sldasm", "m3d", "a3d", "cdw", "frw"], "production.drawing"],
  [["xlsx", "xls", "csv"], "production.specification"],
  [["pdf"], "production.kd"],
];

function extOf(name: string): string {
  return (name.split(".").pop() ?? "").toLowerCase();
}

/** Вид документа по расширению, как `guessKind` прототипа; пользователь меняет до загрузки. */
function guessKind(name: string): string {
  const ext = extOf(name);
  return EXT_KIND.find(([exts]) => exts.includes(ext))?.[1] ?? "production.other";
}

export function DocumentUpload({ orderId, operationId, compact }: { orderId: string; operationId?: string; compact?: boolean }) {
  const { run, pending } = useAction();
  const kinds = useListDocumentKinds({ query: { staleTime: 5 * 60_000 } }).data ?? [];
  const schedule = useGetProductionOrderSchedule(orderId, { query: { enabled: !operationId && !compact } });
  const [files, setFiles] = useState<File[]>([]);
  const [kind, setKind] = useState("");
  const [op, setOp] = useState(operationId ?? "");
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function pick(list: FileList | null) {
    const arr = list ? Array.from(list) : [];
    setFiles(arr);
    if (arr[0]) setKind(guessKind(arr[0].name));
  }

  async function upload() {
    for (const file of files) {
      await run(
        () => uploadProductionOrderDocument(orderId, { file, doc_type_code: kind || guessKind(file.name), operation_id: op || null }),
        `Загружен «${file.name}»`,
      );
    }
    setFiles([]);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div
      className={cn(
        "rounded-xl border-2 border-dashed border-slate-300 text-center text-sm text-muted-foreground transition-colors",
        compact ? "p-2" : "mb-3.5 p-4",
        over && "border-blue-600 bg-blue-50 text-blue-700",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        pick(e.dataTransfer.files);
      }}
    >
      {files.length ? (
        <div className="flex flex-wrap items-end justify-center gap-2 text-left">
          <span className="self-center text-foreground">{files.map((f) => f.name).join(", ")}</span>
          <Field label="Вид" className="w-44">
            <NativeSelect value={kind} onChange={(e) => setKind(e.target.value)} name="doc-kind">
              {kinds.map((k) => (
                <option key={k.code} value={k.code}>
                  {k.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {!operationId && !compact ? (
            <Field label="Операция" className="w-56">
              <NativeSelect value={op} onChange={(e) => setOp(e.target.value)}>
                <option value="">— заказ в целом —</option>
                {(schedule.data?.operations ?? []).map((o, i) => (
                  <option key={o.id} value={o.id}>
                    {i + 1}. {o.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          ) : null}
          <Button size="sm" onClick={upload} disabled={pending}>
            Загрузить
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setFiles([])}>
            Отмена
          </Button>
        </div>
      ) : (
        <>
          {compact ? "Перетащите файл или " : "Перетащите сюда КД, чертежи (dwg, dxf, step, pdf), УП ЧПУ (nc, tap), спецификации — или "}
          <label className="cursor-pointer text-blue-700 underline">
            выберите файлы
            <input ref={inputRef} type="file" multiple hidden data-testid="doc-file-input" onChange={(e) => pick(e.target.files)} />
          </label>
          {!compact ? (
            <div className="mt-1 text-xs">Файл с тем же именем загружается как новое изменение, предыдущее аннулируется.</div>
          ) : null}
        </>
      )}
    </div>
  );
}

export function OrderDocsTab({ order }: { order: OrderOut }) {
  const { run } = useAction();
  const docs = useListProductionOrderDocuments(order.id);
  const schedule = useGetProductionOrderSchedule(order.id);
  const [annul, setAnnul] = useState<{ id: string; name: string } | null>(null);
  const canManage = order.order_abilities.can_manage_documents;
  const opName = new Map((schedule.data?.operations ?? []).map((o, i) => [o.id, `${i + 1}. ${o.name}`]));
  const list = docs.data ?? [];

  return (
    <>
      {canManage ? (
        <DocumentUpload orderId={order.id} />
      ) : (
        <Note>Загружают и утверждают документы конструктор и технолог.</Note>
      )}
      {!order.has_kd ? <Note tone="warn">Нет КД / чертежей — этап «Подготовка производства» не закроется.</Note> : null}
      {list.length ? (
        <table className={TABLE} data-testid="docs-table">
          <thead>
            <tr>
              <th>Вид</th>
              <th>Файл</th>
              <th className="text-center">Изм.</th>
              <th>Операция</th>
              <th>Загружен</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.document_id}>
                <td>{d.doc_type_name}</td>
                <td>
                  <span className="mr-1 rounded bg-slate-200 px-1 py-0.5 text-[10.5px] font-bold text-slate-600 uppercase">{extOf(d.name)}</span>
                  {d.name}
                  <span className="ml-1 text-xs text-muted-foreground">{Math.max(1, Math.round(d.size_bytes / 1024))} КБ</span>
                </td>
                <td className="text-center">{d.version}</td>
                <td>{d.operation_id ? opName.get(d.operation_id) ?? "операция" : <span className="text-muted-foreground">заказ в целом</span>}</td>
                <td className="text-xs whitespace-nowrap text-muted-foreground">{formatDateTime(d.uploaded_at)}</td>
                <td className="whitespace-nowrap">
                  {d.approved_at ? (
                    <Visa>в производство · {d.approved_by_name}</Visa>
                  ) : canManage ? (
                    <Button
                      size="xs"
                      className="bg-emerald-700 hover:bg-emerald-700/90"
                      onClick={() => void run(() => approveProductionOrderDocument(order.id, d.document_id), `«${d.name}» утверждён в производство`)}
                    >
                      Утвердить
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">не утверждён</span>
                  )}
                </td>
                <td className="whitespace-nowrap">
                  <a
                    className="text-blue-700 hover:underline"
                    href={`/api/v1/documents/${d.document_id}/download`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Открыть
                  </a>
                  {canManage ? (
                    <Button size="xs" variant="ghost" className="ml-1 text-destructive" onClick={() => setAnnul({ id: d.document_id, name: d.name })}>
                      Аннулировать
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-muted-foreground">Документов пока нет.</p>
      )}
      <TextDialog
        open={!!annul}
        title={`Аннулировать «${annul?.name ?? ""}»?`}
        description="Документ будет снят с заказа. Причина попадёт в журнал, если указана."
        label="Причина (необязательно)"
        okText="Аннулировать"
        onOpenChange={(open) => !open && setAnnul(null)}
        onSubmit={async (reason) => {
          if (!annul) return;
          const ok = await run(() => annulProductionOrderDocument(order.id, annul.id), "Документ аннулирован");
          if (ok && reason) await run(() => addProductionComment(order.id, { text: `Аннулирован «${annul.name}»: ${reason}` }));
        }}
      />
    </>
  );
}

// --- Журнал ----------------------------------------------------------------------

const KIND_ICON: Record<JournalKind, string> = {
  proc: "📦",
  qc: "🔍",
  comment: "💬",
  visa: "✅",
  status: "▶️",
  stage: "📌",
  plan: "🗓",
  doc: "📎",
};

export function JournalList({
  entries,
}: {
  entries: { id: string; created_at: string; kind: JournalKind; kind_label: string; author_name: string; operation_label: string; stage: string; text: string }[];
}) {
  if (!entries.length) return <p className="py-2 text-sm text-muted-foreground">Записей пока нет.</p>;
  return (
    <ul className="m-0 list-none p-0" data-testid="journal-list">
      {entries.map((j) => (
        <li key={j.id} className="grid grid-cols-[110px_22px_1fr] items-start gap-2.5 border-b border-muted py-2">
          <time className="pt-0.5 text-xs text-muted-foreground tabular-nums">{formatDateTime(j.created_at)}</time>
          <span title={j.kind_label}>{KIND_ICON[j.kind] ?? "•"}</span>
          <div>
            <span className="font-semibold">{j.author_name || "система"}</span>{" "}
            <span className="text-xs text-muted-foreground">
              {j.operation_label ? `операция «${j.operation_label}»` : j.stage ? `этап «${stageTitle(j.stage)}»` : ""}
            </span>
            <div className="mt-0.5 whitespace-pre-wrap">{j.text}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function OrderJournalTab({ order }: { order: OrderOut }) {
  const { run, pending } = useAction();
  const schedule = useGetProductionOrderSchedule(order.id);
  const [kind, setKind] = useState<JournalKind | "">("");
  const [operation, setOperation] = useState("");
  const [author, setAuthor] = useState("");
  const all = useListProductionJournal(order.id).data ?? [];
  const journal = useListProductionJournal(order.id, {
    kind: kind || undefined,
    operation_id: operation || undefined,
    author_id: author || undefined,
  });
  const [target, setTarget] = useState("");
  const [text, setText] = useState("");
  const ops = schedule.data?.operations ?? [];
  const authors = [...new Map(all.filter((j) => j.author_id).map((j) => [j.author_id!, j.author_name])).entries()];

  return (
    <>
      {order.order_abilities.can_comment ? (
        <div className="mb-3.5 grid grid-cols-[260px_1fr_auto] items-end gap-2.5 rounded-xl border p-3">
          <Field label="К чему запись">
            <NativeSelect value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Заказ в целом</option>
              {ops.map((o, i) => (
                <option key={o.id} value={o.id}>
                  Операция {i + 1}: {o.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Запись">
            <TextArea
              className="min-h-9"
              value={text}
              name="journal-text"
              placeholder="Что сделано, проблема, решение…"
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <Button
            disabled={pending || !text.trim()}
            onClick={async () => {
              const ok = await run(() => addProductionComment(order.id, { text: text.trim(), operation_id: target || null }), "Запись добавлена");
              if (ok) setText("");
            }}
          >
            Добавить
          </Button>
        </div>
      ) : null}
      <div className="mb-2.5 flex flex-wrap gap-2">
        <NativeSelect className="w-44" value={author} onChange={(e) => setAuthor(e.target.value)}>
          <option value="">Все авторы</option>
          {authors.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect className="w-44" value={kind} onChange={(e) => setKind(e.target.value as JournalKind | "")} name="journal-kind">
          <option value="">Все типы</option>
          {Object.entries(JOURNAL_KIND_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect className="w-64" value={operation} onChange={(e) => setOperation(e.target.value)}>
          <option value="">Все операции и этапы</option>
          {ops.map((o, i) => (
            <option key={o.id} value={o.id}>
              Операция {i + 1}: {o.name}
            </option>
          ))}
        </NativeSelect>
      </div>
      <JournalList entries={journal.data ?? []} />
    </>
  );
}
