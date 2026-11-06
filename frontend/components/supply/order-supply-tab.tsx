"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useCreateOrderSupplyLine,
  useDeletePurchaseLine,
  useFillOrderSupplyLines,
  useGetOrderSupplyLines,
  useUpdatePurchaseLine,
  type LineOut,
} from "@/lib/api/endpoints";
import { formatDate } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import { LINE_CATEGORY_LABELS, LINE_KIND_LABELS, LateBadge, LineStatusBadge, formatQty, formatRub } from "./labels";
import { LineActionButtons, LineDates, LineHistoryDialog, useInvalidateSupply, useLineActions } from "./line-actions";
import { LineFormDialog } from "./line-form-dialog";

const STEPS = [
  { key: "draft", label: "Черновик", who: "заказ" },
  { key: "sent", label: "Передано в закупку", who: "снабжение" },
  { key: "ordered", label: "Заказано", who: "снабжение" },
  { key: "received", label: "Принято на склад", who: "склад / нач. пр-ва" },
  { key: "issued", label: "Передано в производство", who: "склад / нач. пр-ва" },
] as const;

/**
 * Вкладка «Материалы» (`kind="mat"`) или «Оснастка и расходники» (`kind="tool"`)
 * карточки заказа (`prTab` прототипа): черновики из калькуляции / по маршруту,
 * заявка на закупку из выбранных черновиков, действия по строкам по ролям, история.
 */
export function OrderSupplyTab({ orderId, kind }: { orderId: string; kind: "mat" | "tool" }) {
  const query = useGetOrderSupplyLines(orderId, { kind });
  const invalidate = useInvalidateSupply();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [form, setForm] = useState<{ line: LineOut | null } | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const actions = useLineActions(() => setSelected(new Set()));

  const after = (message: string) => {
    toast.success(message);
    setForm(null);
    void invalidate();
  };
  const fill = useFillOrderSupplyLines({
    mutation: {
      onSuccess: (r) => (r.added ? after(`Добавлено позиций: ${r.added}`) : toast.info("Все позиции уже есть")),
    },
  });
  const create = useCreateOrderSupplyLine({ mutation: { onSuccess: () => after("Позиция добавлена") } });
  const update = useUpdatePurchaseLine({ mutation: { onSuccess: () => after("Позиция изменена") } });
  const remove = useDeletePurchaseLine({ mutation: { onSuccess: () => after("Позиция удалена") } });

  const data = query.data;
  if (query.isLoading) return <p className="text-sm text-muted-foreground">Загрузка…</p>;
  if (!data) return <p className="text-sm text-destructive">Не удалось загрузить потребность заказа.</p>;

  const lines = data.lines;
  const drafts = lines.filter((l) => l.abilities.can_send);
  const chosen = drafts.filter((l) => selected.has(l.id));
  const toSend = chosen.length ? chosen : drafts;
  const late = lines.filter((l) => l.late_days > 0);
  const canRequest = data.abilities.can_request && data.order_open;
  const count = (key: (typeof STEPS)[number]["key"]) =>
    key === "received" ? data.counts.received + data.counts.reserved : data.counts[key];

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-3" data-testid={`order-supply-${kind}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-base font-semibold">{LINE_KIND_LABELS[kind]}</h3>
        <Button
          size="sm"
          variant="outline"
          disabled={!canRequest || fill.isPending}
          onClick={() => fill.mutate({ orderId, params: { kind } })}
        >
          {kind === "mat" ? "Добавить из калькуляции" : "Подобрать по маршруту"}
        </Button>
        <Button size="sm" variant="outline" disabled={!canRequest} onClick={() => setForm({ line: null })}>
          <Plus className="size-4" aria-hidden />
          позиция
        </Button>
        <Button
          size="sm"
          disabled={!toSend.length || actions.pending}
          onClick={() => {
            if (toSend.some((l) => !l.name.trim() || Number(l.quantity) <= 0)) {
              toast.error("У каждой позиции должны быть наименование и количество.");
              return;
            }
            actions.run("send", toSend);
          }}
        >
          Создать заявку на закупку ({toSend.length})
        </Button>
      </div>

      <ol className="flex flex-wrap items-stretch gap-2 text-xs">
        {STEPS.map((step) => (
          <li
            key={step.key}
            className={cn(
              "flex min-w-32 flex-col rounded-md border px-3 py-2",
              count(step.key) ? "border-primary/40 bg-primary/5" : "text-muted-foreground",
            )}
          >
            <b className="text-base">{count(step.key)}</b>
            <span>{step.label}</span>
            <i className="text-muted-foreground">{step.who}</i>
          </li>
        ))}
      </ol>

      {late.length > 0 && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Опаздывают к потребности: {late.map((l) => `${l.name} (+${l.late_days} дн.)`).join(", ")}
        </p>
      )}
      <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
        {kind === "mat"
          ? "Позиции берутся из калькуляции; срок потребности — окончание операции снабжения в плане."
          : "Подбор по маршруту — по участкам, через которые идёт заказ; срок — за 2 рабочих дня до начала операции."}{" "}
        Отметьте черновики и создайте заявку на закупку — она получит номер и уйдёт в отдел закупок; если
        ничего не отмечено, в заявку попадут все черновики.
        {data.requisitions.length > 0 && ` Заявки по заказу: ${data.requisitions.join(", ")}.`}
      </p>

      {lines.length === 0 ? (
        <p className="text-sm text-muted-foreground">Позиций нет.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <Checkbox
                    aria-label="Отметить все черновики"
                    checked={drafts.length > 0 && chosen.length === drafts.length}
                    onCheckedChange={(on) => setSelected(on ? new Set(drafts.map((l) => l.id)) : new Set())}
                    disabled={!drafts.length}
                  />
                </TableHead>
                {kind === "tool" && <TableHead>Кат.</TableHead>}
                <TableHead>Наименование</TableHead>
                <TableHead className="text-right">Кол-во</TableHead>
                <TableHead className="text-right">Цена</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead>Для операции</TableHead>
                <TableHead>Нужно к</TableHead>
                <TableHead>Статус · заявка</TableHead>
                <TableHead>Поставщик</TableHead>
                <TableHead>Сроки</TableHead>
                <TableHead>Действие</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => (
                <TableRow
                  key={line.id}
                  className={cn("cursor-pointer", line.late_days > 0 && "bg-destructive/5")}
                  onClick={() => setHistoryId(line.id)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {line.abilities.can_send && (
                      <Checkbox
                        aria-label={`Отметить ${line.name}`}
                        checked={selected.has(line.id)}
                        onCheckedChange={(on) => toggle(line.id, !!on)}
                      />
                    )}
                  </TableCell>
                  {kind === "tool" && <TableCell>{LINE_CATEGORY_LABELS[line.category]}</TableCell>}
                  <TableCell className="max-w-64 whitespace-normal">{line.name}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {formatQty(line.quantity)} {line.unit}
                  </TableCell>
                  <TableCell className="text-right">{formatRub(line.price)}</TableCell>
                  <TableCell className="text-right">{formatRub(line.amount)}</TableCell>
                  <TableCell className="max-w-48 truncate text-xs text-muted-foreground">
                    {line.operation_name || "—"}
                  </TableCell>
                  <TableCell>{formatDate(line.need_date)}</TableCell>
                  <TableCell>
                    <LineStatusBadge status={line.status} />
                    {line.requisition_no && <div className="text-xs text-muted-foreground">{line.requisition_no}</div>}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {line.supplier_name}
                    {line.po_number && <div>{line.po_number}</div>}
                  </TableCell>
                  <TableCell>
                    <LineDates line={line} />
                    <LateBadge days={line.late_days} />
                  </TableCell>
                  <TableCell>
                    {line.status === "draft" ? (
                      <span className="text-xs text-muted-foreground">отметьте и создайте заявку</span>
                    ) : (
                      <LineActionButtons line={line} run={actions.run} disabled={actions.pending} />
                    )}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {line.abilities.can_edit && (
                      <div className="flex gap-1">
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Изменить ${line.name}`}
                          onClick={() => setForm({ line })}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Удалить ${line.name}`}
                          disabled={remove.isPending}
                          onClick={() => remove.mutate({ lineId: line.id })}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {form && (
        <LineFormDialog
          key={form.line?.id ?? "new"}
          open
          kind={kind}
          line={form.line}
          operations={data.operations}
          pending={create.isPending || update.isPending}
          onClose={() => setForm(null)}
          onSubmit={(payload) =>
            form.line
              ? update.mutate({ lineId: form.line.id, data: payload })
              : create.mutate({ orderId, data: payload })
          }
        />
      )}
      {actions.element}
      <LineHistoryDialog lineId={historyId} onClose={() => setHistoryId(null)} />
    </div>
  );
}
