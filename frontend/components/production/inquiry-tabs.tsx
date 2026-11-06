"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  addCalcMaterial,
  addCalcOperation,
  buildInquiryPlan,
  deleteCalcMaterial,
  deleteCalcOperation,
  fillInquiryFromTemplate,
  linkCalcOperationsSequentially,
  setCalcOperationPredecessors,
  setInquiryStageResponsible,
  updateCalcMaterial,
  updateCalcOperation,
  updateInquiry,
  useListProductionEmployees,
  useListProductTemplates,
  useListWorkCenters,
  type CalcOperationIn,
  type CalcOperationOut,
  type InquiryOut,
  type InquiryUpdateIn,
} from "@/lib/api/endpoints";
import { addWorkingDays, fd, fdl, nextWorkingDay, todayIso, workingDaysBetween } from "@/lib/production/dates";
import { hours, num, rub } from "@/lib/production/format";
import { useAction } from "@/lib/production/use-action";
import { formatDateTime } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import { CellInput, CellSelect, Field, Line, NativeSelect, Note, Pill, SectionTitle, TABLE, TextInput, Visa } from "./bits";
import { GanttChart, type GanttRow } from "./gantt-chart";

function inquiryPayload(inquiry: InquiryOut, patch: Partial<InquiryUpdateIn> = {}): InquiryUpdateIn {
  return {
    object_name: inquiry.object_name,
    product_name: inquiry.product_name,
    template_id: inquiry.template_id,
    quantity: inquiry.quantity,
    due_date: inquiry.due_date,
    manager_id: inquiry.manager_id,
    overhead_pct: inquiry.overhead_pct,
    margin_pct: inquiry.margin_pct,
    vat_pct: inquiry.vat_pct,
    ...patch,
  };
}

function opPayload(op: CalcOperationOut, patch: Partial<CalcOperationIn> = {}): CalcOperationIn {
  return {
    name: op.name,
    work_center_id: op.work_center_id,
    hours: op.hours,
    people: op.people,
    not_before: op.not_before,
    ...patch,
  };
}

// --- Основное --------------------------------------------------------------------

export function InquiryMainTab({ inquiry, onGoCalc }: { inquiry: InquiryOut; onGoCalc: () => void }) {
  const { run, pending } = useAction();
  const employees = useListProductionEmployees({ query: { staleTime: 5 * 60_000 } }).data ?? [];
  const templates = useListProductTemplates({ query: { staleTime: 5 * 60_000 } }).data ?? [];
  const canEdit = inquiry.abilities.can_edit;
  const [form, setForm] = useState(() => inquiryPayload(inquiry));
  useEffect(() => setForm(inquiryPayload(inquiry)), [inquiry]);
  const dirty = JSON.stringify(form) !== JSON.stringify(inquiryPayload(inquiry));
  const set = (patch: Partial<InquiryUpdateIn>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <>
      {inquiry.stage === "lost" ? (
        <Note tone="bad">
          Заявка проиграна: <b>{inquiry.lost_reason_name}</b>
          {inquiry.lost_comment ? ` — ${inquiry.lost_comment}` : ""}
        </Note>
      ) : null}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label="Заказчик">
          <TextInput value={inquiry.customer_name} disabled />
        </Field>
        <Field label="Объект">
          <TextInput value={form.object_name} disabled={!canEdit} onChange={(e) => set({ object_name: e.target.value })} />
        </Field>
        <Field label="Изделие">
          <TextInput value={form.product_name} disabled={!canEdit} onChange={(e) => set({ product_name: e.target.value })} />
        </Field>
        <Field label="Тип изделия (шаблон калькуляции и маршрута)">
          <NativeSelect value={form.template_id ?? ""} disabled={!canEdit} onChange={(e) => set({ template_id: e.target.value || null })}>
            <option value="">—</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.code} — {t.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Количество, шт.">
          <TextInput type="number" min={1} value={String(form.quantity)} disabled={!canEdit} onChange={(e) => set({ quantity: e.target.value })} />
        </Field>
        <Field label="Требуемый срок">
          <TextInput type="date" value={form.due_date} disabled={!canEdit} onChange={(e) => set({ due_date: e.target.value })} />
        </Field>
        <Field label="Менеджер проекта">
          <NativeSelect value={form.manager_id} disabled={!canEdit} onChange={(e) => set({ manager_id: e.target.value })}>
            {!employees.some((e) => e.id === inquiry.manager_id) ? <option value={inquiry.manager_id}>{inquiry.manager_name}</option> : null}
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.full_name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Дата регистрации">
          <TextInput value={formatDateTime(inquiry.created_at)} disabled />
        </Field>
      </div>
      {canEdit && dirty ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={pending} onClick={() => void run(() => updateInquiry(inquiry.id, form), "Заявка сохранена")}>
            Сохранить
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setForm(inquiryPayload(inquiry))}>
            Отменить
          </Button>
        </div>
      ) : null}
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
              {inquiry.approvals.map((a) => (
                <tr key={a.stage} className={cn(a.stage === inquiry.stage && "bg-blue-50")}>
                  <td>{a.stage_label}</td>
                  <td>
                    <CellSelect
                      value={a.responsible_id ?? ""}
                      disabled={!canEdit || !!a.approved_at}
                      onChange={(e) =>
                        void run(() => setInquiryStageResponsible(inquiry.id, a.stage, { responsible_id: e.target.value }), "Ответственный назначен")
                      }
                    >
                      <option value="">—</option>
                      {a.responsible_id && !employees.some((e) => e.id === a.responsible_id) ? (
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
                      </Visa>
                    ) : a.stage === "new" ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">нет</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {inquiry.abilities.can_edit_calculation && !inquiry.operations.length && inquiry.template_id ? (
            <Button
              variant="outline"
              className="mt-2.5"
              onClick={async () => {
                const ok = await run(() => fillInquiryFromTemplate(inquiry.id, { template_id: inquiry.template_id }), "Калькуляция и маршрут заполнены по шаблону");
                if (ok) onGoCalc();
              }}
            >
              Заполнить калькуляцию и маршрут по шаблону
            </Button>
          ) : null}
        </div>
        <div className="rounded-xl border px-3.5 py-2.5 text-[13px]">
          <Line label="Себестоимость" value={rub(inquiry.totals.cost)} />
          <Line label="Трудоёмкость" value={`${hours(inquiry.totals.hours)} н-ч`} />
          <Line label="Начало" value={fdl(inquiry.planned_start)} />
          <Line label="Окончание" value={fdl(inquiry.planned_finish)} />
          <Line label="Длительность" value={inquiry.plan_length ? `${inquiry.plan_length} раб. дн.` : "—"} />
          <Line label="Вероятность" value={`${Math.round(num(inquiry.probability))}%`} />
          <Line label="Цена с НДС" value={rub(inquiry.totals.total)} big />
        </div>
      </div>
    </>
  );
}

// --- Калькуляция -----------------------------------------------------------------

/** Таблицы материалов и маршрута с итогами — редактируемые у заявки, только чтение у заказа. */
export function CalcTables({ inquiry, readOnly }: { inquiry: InquiryOut; readOnly?: boolean }) {
  const { run } = useAction();
  const centers = useListWorkCenters({ query: { staleTime: 5 * 60_000 } }).data ?? [];
  const templates = useListProductTemplates({ query: { staleTime: 5 * 60_000, enabled: !readOnly } }).data ?? [];
  const [templateId, setTemplateId] = useState(inquiry.template_id ?? "");
  const lock = readOnly || !inquiry.abilities.can_edit_calculation;
  const T = inquiry.totals;
  const activeCenters = centers.filter((c) => c.is_active);

  return (
    <>
      {!readOnly && lock ? <Note>Калькуляцию ведут экономист и менеджер заявки — здесь только просмотр.</Note> : null}
      {!lock ? (
        <div className="mb-2 flex flex-wrap items-end gap-2">
          <Field label="Шаблон изделия" className="w-64">
            <NativeSelect value={templateId} onChange={(e) => setTemplateId(e.target.value)} name="fill-template">
              <option value="">— тип изделия заявки —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.code} — {t.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Button
            variant="outline"
            onClick={() =>
              void run(
                () => fillInquiryFromTemplate(inquiry.id, { template_id: templateId || null }),
                "Калькуляция и маршрут заполнены из шаблона",
              )
            }
          >
            Заполнить из шаблона
          </Button>
          {inquiry.operations.length || inquiry.materials.length ? (
            <span className="pb-1.5 text-xs text-muted-foreground">Текущие строки калькуляции будут заменены.</span>
          ) : null}
        </div>
      ) : null}
      <SectionTitle>Материалы и комплектующие</SectionTitle>
      <table className={TABLE} data-testid="calc-materials">
        <thead>
          <tr>
            <th>Наименование</th>
            <th className="w-24 text-right">Кол-во</th>
            <th className="w-32 text-right">Цена, ₽</th>
            <th className="w-36 text-right">Сумма</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {inquiry.materials.map((m) => {
            const save = (patch: { name?: string; quantity?: string; price?: string }) =>
              void run(() => updateCalcMaterial(m.id, { name: m.name, quantity: m.quantity, price: m.price, ...patch }));
            return (
              <tr key={m.id}>
                <td>
                  <CellInput
                    defaultValue={m.name}
                    key={`n${m.name}`}
                    disabled={lock}
                    onBlur={(e) => e.target.value !== m.name && save({ name: e.target.value })}
                  />
                </td>
                <td>
                  <CellInput
                    type="number"
                    className="text-right"
                    defaultValue={num(m.quantity)}
                    key={`q${m.quantity}`}
                    disabled={lock}
                    onBlur={(e) => num(e.target.value) !== num(m.quantity) && save({ quantity: e.target.value || "0" })}
                  />
                </td>
                <td>
                  <CellInput
                    type="number"
                    className="text-right"
                    defaultValue={num(m.price)}
                    key={`p${m.price}`}
                    disabled={lock}
                    onBlur={(e) => num(e.target.value) !== num(m.price) && save({ price: e.target.value || "0" })}
                  />
                </td>
                <td className="text-right tabular-nums">{rub(m.amount)}</td>
                <td>
                  {!lock ? (
                    <button type="button" className="px-1 text-lg leading-none text-slate-400 hover:text-red-600" aria-label="Удалить" onClick={() => void run(() => deleteCalcMaterial(m.id))}>
                      ×
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!lock ? (
        <Button size="xs" variant="outline" className="mt-1.5" onClick={() => void run(() => addCalcMaterial(inquiry.id, { name: "Новая позиция", quantity: "1", price: "0" }))}>
          + позиция
        </Button>
      ) : null}

      <SectionTitle>Маршрут и трудоёмкость</SectionTitle>
      <table className={TABLE} data-testid="calc-operations">
        <thead>
          <tr>
            <th>Операция</th>
            <th className="w-60">Участок</th>
            <th className="w-24 text-right">Н-ч / дней</th>
            <th className="w-20 text-right">Ставка</th>
            <th className="w-32 text-right">Сумма</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {inquiry.operations.map((op) => {
            const save = (patch: Partial<CalcOperationIn>) => void run(() => updateCalcOperation(op.id, opPayload(op, patch)));
            return (
              <tr key={op.id}>
                <td>
                  <CellInput defaultValue={op.name} key={`n${op.name}`} disabled={lock} onBlur={(e) => e.target.value !== op.name && save({ name: e.target.value })} />
                </td>
                <td>
                  <CellSelect value={op.work_center_id} disabled={lock} onChange={(e) => save({ work_center_id: e.target.value })}>
                    {!activeCenters.some((c) => c.id === op.work_center_id) ? <option value={op.work_center_id}>{op.work_center_name}</option> : null}
                    {activeCenters.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </CellSelect>
                </td>
                <td>
                  <CellInput
                    type="number"
                    step="0.5"
                    className="text-right"
                    title={op.is_supply ? "Срок поставки, рабочих дней" : "Нормо-часы"}
                    defaultValue={num(op.hours)}
                    key={`h${op.hours}`}
                    disabled={lock}
                    onBlur={(e) => num(e.target.value) !== num(op.hours) && save({ hours: e.target.value || "0" })}
                  />
                </td>
                <td className="text-right">{op.is_supply ? "—" : rub(op.rate)}</td>
                <td className="text-right tabular-nums">
                  {op.is_supply ? <span className="text-xs text-muted-foreground">{hours(op.hours)} дн.</span> : rub(num(op.hours) * num(op.rate))}
                </td>
                <td>
                  {!lock ? (
                    <button type="button" className="px-1 text-lg leading-none text-slate-400 hover:text-red-600" aria-label="Удалить" onClick={() => void run(() => deleteCalcOperation(op.id))}>
                      ×
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!lock ? (
        <Button
          size="xs"
          variant="outline"
          className="mt-1.5"
          disabled={!activeCenters.length}
          onClick={() => {
            const center = activeCenters.find((c) => !c.is_supply) ?? activeCenters[0];
            void run(() => addCalcOperation(inquiry.id, { name: "Новая операция", work_center_id: center.id, hours: "8", people: 1 }));
          }}
        >
          + операция
        </Button>
      ) : null}

      <div className="mt-3.5 grid grid-cols-[1fr_290px] gap-5">
        <div>
          <SectionTitle>Параметры</SectionTitle>
          <div className="flex flex-wrap items-end gap-3">
            {(
              [
                ["overhead_pct", "Накладные, % ФОТ"],
                ["margin_pct", "Рентабельность, %"],
                ["vat_pct", "НДС, %"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label} className="w-32">
                <TextInput
                  type="number"
                  defaultValue={num(inquiry[key])}
                  key={`${key}${inquiry[key]}`}
                  disabled={lock || !inquiry.abilities.can_edit}
                  onBlur={(e) => {
                    if (num(e.target.value) !== num(inquiry[key]))
                      void run(() => updateInquiry(inquiry.id, inquiryPayload(inquiry, { [key]: e.target.value || "0" })));
                  }}
                />
              </Field>
            ))}
          </div>
          <Note>
            Для операций снабжения указывается срок поставки в рабочих днях — стоимость закупки входит в материалы. Связи
            между операциями задаются на вкладке «План».
          </Note>
        </div>
        <div className="rounded-xl border px-3.5 py-2.5 text-[13px]" data-testid="calc-totals">
          <Line label="Материалы" value={rub(T.materials)} />
          <Line label={`Труд (${hours(T.hours)} н-ч)`} value={rub(T.labor)} />
          <Line label="Накладные" value={rub(T.overhead)} />
          <Line label={<b>Себестоимость</b>} value={<b>{rub(T.cost)}</b>} />
          <Line label="Прибыль" value={rub(T.profit)} />
          <Line label="Цена без НДС" value={rub(T.price)} />
          <Line label="НДС" value={rub(T.vat)} />
          <Line label="Итого" value={rub(T.total)} big />
        </div>
      </div>
    </>
  );
}

// --- План ------------------------------------------------------------------------

export function inquiryToGantt(inquiry: InquiryOut): GanttRow {
  return {
    id: inquiry.id,
    number: inquiry.number,
    customer_name: inquiry.customer_name,
    product_name: inquiry.product_name,
    stage: inquiry.stage,
    due_date: inquiry.due_date,
    planned_start: inquiry.planned_start,
    planned_finish: inquiry.planned_finish,
    health: inquiry.health,
    can_plan: false,
    tentative: true,
    operations: inquiry.operations.map((o) => ({
      ...o,
      status: "wait" as const,
      progress: 0,
      responsible_name: "",
      violates_dependency: false,
    })),
  };
}

export function InquiryPlanTab({ inquiry }: { inquiry: InquiryOut }) {
  const { run } = useAction();
  const lock = !inquiry.abilities.can_edit_calculation;
  const ops = inquiry.operations;
  const numberOf = useMemo(() => new Map(ops.map((o, i) => [o.id, i + 1])), [ops]);
  const byId = useMemo(() => new Map(ops.map((o) => [o.id, o])), [ops]);
  const defStart = inquiry.planned_start ?? nextWorkingDay(addWorkingDays(todayIso(), 5));
  const [start, setStart] = useState(defStart);
  useEffect(() => setStart(defStart), [defStart]);
  const hasPlan = inquiry.has_plan;
  const late = inquiry.planned_finish && inquiry.planned_finish > inquiry.due_date;

  function savePredecessors(op: CalcOperationOut, value: string) {
    const numbers = value.split(/[,;\s]+/).filter(Boolean).map(Number);
    const current = op.predecessor_ids.map((id) => numberOf.get(id)).sort((a, b) => a! - b!).join(", ");
    if ([...numbers].sort((a, b) => a - b).join(", ") === current) return;
    if (numbers.some((n) => !Number.isInteger(n) || n < 1 || n > ops.length || ops[n - 1].id === op.id)) {
      toast.error("Неверный номер операции в предшественниках.");
      return;
    }
    void run(() => setCalcOperationPredecessors(op.id, { predecessor_ids: numbers.map((n) => ops[n - 1].id) }), "Связи сохранены");
  }

  return (
    <>
      <Note>
        Колонка <b>«Предш.»</b> — номера операций, после окончания которых начинается эта (через запятую). Операции с общим
        предшественником идут <b>параллельно</b>. Длительность = н-ч ÷ (8 ч × исполнителей), для снабжения — срок поставки;
        всё в рабочих днях. <b>«Не ранее»</b> — ограничение даты начала.
      </Note>
      <div className="flex flex-wrap items-end gap-2.5">
        <Field label="Начало работ" className="w-40">
          <TextInput type="date" value={start} disabled={lock} onChange={(e) => setStart(e.target.value)} name="plan-start" />
        </Field>
        <Button
          variant={hasPlan ? "outline" : "default"}
          disabled={lock || !ops.length}
          onClick={() => void run(() => buildInquiryPlan(inquiry.id, { planned_start: start }), hasPlan ? "План пересчитан" : "План сформирован")}
        >
          {hasPlan ? "Пересчитать план" : "Сформировать план"}
        </Button>
        <Button variant="outline" disabled={lock || ops.length < 2} onClick={() => void run(() => linkCalcOperationsSequentially(inquiry.id), "Операции связаны последовательно")}>
          Связать всё последовательно
        </Button>
        <span className="flex-1" />
        {hasPlan && inquiry.planned_finish ? (
          <span className="text-sm">
            Окончание <b>{fdl(inquiry.planned_finish)}</b> · {inquiry.plan_length} раб. дн. · срок {fdl(inquiry.due_date)}{" "}
            <Pill tone={late ? "r" : "g"}>
              {late
                ? `позже на ${workingDaysBetween(inquiry.due_date, inquiry.planned_finish)} раб. дн.`
                : `запас ${workingDaysBetween(inquiry.planned_finish, inquiry.due_date)} раб. дн.`}
            </Pill>
          </span>
        ) : null}
      </div>
      {inquiry.critical_path.length ? (
        <Note tone="crit">
          <b>Критический путь ({inquiry.plan_length} раб. дн.):</b>{" "}
          {inquiry.critical_path.map((id) => `${numberOf.get(id)}. ${byId.get(id)?.name ?? ""}`).join(" → ")}
        </Note>
      ) : null}
      <table className={cn(TABLE, "mt-3")} data-testid="inquiry-plan-table">
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
          </tr>
        </thead>
        <tbody>
          {ops.map((op, i) => (
            <tr key={op.id} className={cn(op.is_critical && "bg-orange-50")}>
              <td className="text-muted-foreground">{i + 1}</td>
              <td>{op.name}</td>
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
                    disabled={lock}
                    onBlur={(e) => {
                      const v = Math.min(op.capacity, Math.max(1, Number(e.target.value) || 1));
                      if (v !== op.people) void run(() => updateCalcOperation(op.id, opPayload(op, { people: v })));
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
                  disabled={lock}
                  onBlur={(e) => savePredecessors(op, e.target.value)}
                />
              </td>
              <td>
                <CellInput
                  type="date"
                  defaultValue={op.not_before ?? ""}
                  key={`n${op.not_before}`}
                  disabled={lock}
                  onBlur={(e) => {
                    const v = e.target.value || null;
                    if (v !== op.not_before) void run(() => updateCalcOperation(op.id, opPayload(op, { not_before: v })));
                  }}
                />
              </td>
              <td>{fd(op.planned_start)}</td>
              <td>{fd(op.planned_finish)}</td>
              <td className="text-right">{op.slack == null ? "—" : op.slack <= 0 ? <b className="text-orange-700">0</b> : `${op.slack} дн.`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <SectionTitle>Сетевой график</SectionTitle>
      {hasPlan ? <GanttChart rows={[inquiryToGantt(inquiry)]} mini /> : <p className="text-sm text-muted-foreground">План ещё не сформирован.</p>}
    </>
  );
}
