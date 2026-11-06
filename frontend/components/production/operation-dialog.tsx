"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { OperationQcPanel } from "@/components/quality/operation-qc-panel";
import {
  addProductionComment,
  updateProductionOperation,
  useGetProductionOperation,
  useGetProductionOrder,
  useListProductionEmployees,
  type OperationLinkOut,
} from "@/lib/api/endpoints";
import { fd, workIndex } from "@/lib/production/dates";
import { hours } from "@/lib/production/format";
import { OPERATION_STATUS_LABELS } from "@/lib/production/stages";
import { useAction } from "@/lib/production/use-action";

import { Field, NativeSelect, Pill, SectionTitle, TextArea, TextInput, Visa } from "./bits";
import { useCards } from "./card-host";
import { DocumentUpload, JournalList, OperationVisaButton, ProgressSlider, StatusSelect } from "./order-tabs";

const STATUS_TONE = { done: "g", check: "y", work: "b", wait: "n" } as const;

/** Карточка операции — модальное окно (`opDialog` прототипа). */
export function OperationDialog({
  operationId,
  onOpenChange,
}: {
  operationId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [current, setCurrent] = useState(operationId);
  useEffect(() => setCurrent(operationId), [operationId]);

  return (
    <Dialog open={!!operationId} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-auto sm:max-w-[1000px]" data-testid="operation-dialog">
        {current ? <OperationBody operationId={current} onSwitch={setCurrent} onClose={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function OperationBody({
  operationId,
  onSwitch,
  onClose,
}: {
  operationId: string;
  onSwitch: (id: string) => void;
  onClose: () => void;
}) {
  const { run, pending } = useAction();
  const cards = useCards();
  const query = useGetProductionOperation(operationId);
  const card = query.data && query.data.operation.id === operationId ? query.data : undefined;
  const orderQuery = useGetProductionOrder(card?.order.id ?? "", { query: { enabled: !!card } });
  const employees = useListProductionEmployees({ query: { staleTime: 5 * 60_000 } }).data ?? [];
  const [comment, setComment] = useState("");

  if (!card) {
    return (
      <div className="flex flex-col gap-3">
        <DialogTitle className="sr-only">Операция</DialogTitle>
        <Skeleton className="h-6 w-80" />
        <Skeleton className="h-60 w-full" />
      </div>
    );
  }

  const op = card.operation;
  const order = card.order;
  const ab = op.abilities;
  const canDocs = orderQuery.data?.order_abilities.can_manage_documents ?? false;
  const canComment = orderQuery.data?.order_abilities.can_comment ?? false;
  const started = ["prep", "prod", "qc"].includes(order.stage);

  const link = (x: OperationLinkOut) => (
    <div key={x.id} className="my-0.5">
      <button type="button" className="text-blue-700 hover:underline" onClick={() => onSwitch(x.id)}>
        {x.name}
      </button>{" "}
      <Pill tone={STATUS_TONE[x.status]}>{OPERATION_STATUS_LABELS[x.status]}</Pill>{" "}
      <span className="text-xs text-muted-foreground">
        {fd(x.planned_start)}–{fd(x.planned_finish)}
      </span>
    </div>
  );

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 pr-8">
        <DialogTitle className="text-base font-semibold">{op.name}</DialogTitle>
        <Pill tone={STATUS_TONE[op.status]}>{OPERATION_STATUS_LABELS[op.status]}</Pill>
        {op.is_critical ? <Pill tone="c">критический путь</Pill> : op.slack != null ? <Pill>резерв {op.slack} раб. дн.</Pill> : null}
        {op.violates_dependency ? <Pill tone="r">нарушение связи</Pill> : null}
        {op.approved_at ? (
          <Visa>
            виза {op.approved_by_name}
            {op.approved_for_name ? ` за ${op.approved_for_name}` : ""} · {fd(op.approved_at.slice(0, 10))}
          </Visa>
        ) : null}
      </div>
      <div className="mt-1 mb-3 text-xs text-muted-foreground">
        {order.number} · {order.product_name} × {Number(order.quantity)} · {order.customer_name} · <b>{op.work_center_name}</b>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div>
          <div className="grid grid-cols-2 gap-2.5">
            <Field label="Ответственный">
              <NativeSelect
                value={op.responsible_id ?? ""}
                disabled={!ab.can_set_responsible}
                name="op-responsible"
                onChange={(e) =>
                  e.target.value && void run(() => updateProductionOperation(op.id, { responsible_id: e.target.value }), "Ответственный назначен")
                }
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
              </NativeSelect>
            </Field>
            <Field label="Статус">
              {started && op.status !== "done" ? (
                <div className="h-8 rounded-md border border-input">
                  <StatusSelect op={op} />
                </div>
              ) : (
                <TextInput value={OPERATION_STATUS_LABELS[op.status]} disabled />
              )}
            </Field>
            <Field label="План">
              <TextInput
                value={
                  op.planned_start
                    ? `${fd(op.planned_start)} – ${fd(op.planned_finish)} · ${op.planned_finish ? workIndex(op.planned_finish) - workIndex(op.planned_start) + 1 : op.duration} раб. дн.`
                    : "—"
                }
                disabled
              />
            </Field>
            <Field label={op.is_supply ? "Срок поставки, дн." : "Трудоёмкость, н-ч"}>
              <TextInput value={op.is_supply ? hours(op.hours) : `${hours(op.hours)} · освоено ${hours(op.earned_hours)}`} disabled />
            </Field>
            {!op.is_supply ? (
              <Field label={`Исполнителей (макс. ${op.capacity})`}>
                <TextInput
                  type="number"
                  min={1}
                  max={op.capacity}
                  defaultValue={op.people}
                  key={`p${op.people}`}
                  disabled={!ab.can_edit_plan}
                  onBlur={(e) => {
                    const v = Math.min(op.capacity, Math.max(1, Number(e.target.value) || 1));
                    if (v !== op.people) void run(() => updateProductionOperation(op.id, { people: v }), "Исполнители изменены");
                  }}
                />
              </Field>
            ) : null}
            <Field label="Не ранее">
              <TextInput
                type="date"
                defaultValue={op.not_before ?? ""}
                key={`n${op.not_before}`}
                disabled={!ab.can_edit_plan}
                onBlur={(e) => {
                  const v = e.target.value || null;
                  if (v !== op.not_before)
                    void run(() => updateProductionOperation(op.id, { not_before: v }), v ? "Ограничение «не ранее» задано" : "Ограничение снято");
                }}
              />
            </Field>
          </div>
          {!op.is_supply && (op.status === "work" || ab.can_set_progress) ? (
            <Field label="Выполнено" className="mt-2.5">
              <ProgressSlider op={op} />
            </Field>
          ) : null}

          <SectionTitle>Связи</SectionTitle>
          <div className="text-xs text-muted-foreground">Предшественники — начинается после них</div>
          {card.predecessors.length ? card.predecessors.map(link) : <div className="text-xs text-muted-foreground">— нет, стартует с начала заказа</div>}
          <div className="mt-2 text-xs text-muted-foreground">Последователи — ждут эту операцию</div>
          {card.successors.length ? card.successors.map(link) : <div className="text-xs text-muted-foreground">— нет, завершающая</div>}

          <SectionTitle>Документы операции</SectionTitle>
          {card.documents.length ? (
            card.documents.map((d) => (
              <div key={d.document_id} className="my-0.5 text-[13px]">
                <a className="text-blue-700 hover:underline" href={`/api/v1/documents/${d.document_id}/download`} target="_blank" rel="noreferrer">
                  {d.name}
                </a>{" "}
                <span className="text-xs text-muted-foreground">
                  {d.doc_type_name} · изм. {d.version}
                </span>{" "}
                {d.approved_at ? <Visa>утв.</Visa> : null}
              </div>
            ))
          ) : (
            <div className="text-xs text-muted-foreground">Нет привязанных документов.</div>
          )}
          {canDocs ? (
            <div className="mt-1.5">
              <DocumentUpload orderId={order.id} operationId={op.id} compact />
            </div>
          ) : null}
        </div>
        <div>
          {/* Заголовок, предупреждение «записей нет» и право записи (`abilities.can_record`)
              — внутри блока ОТК: он сам читает их с сервера. */}
          <OperationQcPanel operationId={op.id} workCenterId={op.work_center_id} />
        </div>
      </div>

      <SectionTitle>Журнал операции</SectionTitle>
      <div className="flex items-stretch gap-2">
        <TextArea
          className="min-h-11 flex-1"
          placeholder="Комментарий"
          value={comment}
          disabled={!canComment}
          name="op-comment"
          onChange={(e) => setComment(e.target.value)}
        />
        <div className="flex flex-col gap-1.5">
          <Button
            variant="outline"
            disabled={!canComment || !comment.trim() || pending}
            onClick={async () => {
              const ok = await run(() => addProductionComment(order.id, { text: comment.trim(), operation_id: op.id }), "Запись добавлена");
              if (ok) setComment("");
            }}
          >
            Комментарий
          </Button>
          {op.status !== "done" && started ? <OperationVisaButton op={op} size="sm" /> : null}
        </div>
      </div>
      <JournalList entries={card.journal} />
      <div className="mt-3 flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={() => {
            onClose();
            cards.openOrder(order.id, "state");
          }}
        >
          Карточка заказа
        </Button>
        <Button variant="outline" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  );
}
