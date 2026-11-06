"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { OptionSelect } from "@/components/option-select/option-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useChangePurchaseLinesEta,
  useCreateSupplier,
  useGetPurchaseLine,
  useGetSupplyReference,
  useIssuePurchaseLines,
  useListWorkCenters,
  useOrderPurchaseLines,
  useReceivePurchaseLines,
  useReservePurchaseLines,
  useSendPurchaseLines,
  type LineOut,
} from "@/lib/api/endpoints";
import { formatDate, formatDateTime } from "@/lib/format/ru";

import { addDaysIso, formatQty, formatRub, todayIso } from "./labels";

export type LineAction = "send" | "order" | "eta" | "receive" | "reserve" | "issue";

/** Сброс кэша после действия: реестр снабжения и журнал заказа (`production`). */
export function useInvalidateSupply() {
  const queryClient = useQueryClient();
  return () =>
    queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey[0];
        return typeof key === "string" && (key.startsWith("/api/v1/supply") || key.startsWith("/api/v1/production"));
      },
    });
}

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 86_400_000);
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

/**
 * Действия над строками потребности (`prAction` прототипа) — для одной строки и для
 * выбранных. Передача в закупку и резерв выполняются сразу, остальное — через диалог.
 * Возвращает `run(action, lines)` и элемент диалогов, который нужно отрисовать.
 */
export function useLineActions(onDone?: () => void) {
  const invalidate = useInvalidateSupply();
  const [dialog, setDialog] = useState<{ action: LineAction; lines: LineOut[] } | null>(null);

  const finish = (message: string) => {
    toast.success(message);
    setDialog(null);
    void invalidate();
    onDone?.();
  };

  const send = useSendPurchaseLines({
    mutation: { onSuccess: (r) => finish(`Создана заявка ${r.requisition_no} — передана в отдел закупок`) },
  });
  const reserve = useReservePurchaseLines({ mutation: { onSuccess: () => finish("Зарезервировано со склада") } });

  const run = (action: LineAction, lines: LineOut[]) => {
    if (!lines.length) return;
    const ids = lines.map((l) => l.id);
    if (action === "send") send.mutate({ data: { line_ids: ids } });
    else if (action === "reserve") reserve.mutate({ data: { line_ids: ids } });
    else setDialog({ action, lines });
  };

  const element = dialog ? (
    <ActionDialog
      key={`${dialog.action}-${dialog.lines.map((l) => l.id).join()}`}
      action={dialog.action}
      lines={dialog.lines}
      onClose={() => setDialog(null)}
      onDone={finish}
    />
  ) : null;

  return { run, element, pending: send.isPending || reserve.isPending };
}

const TITLES: Record<LineAction, string> = {
  send: "Передать в закупку",
  order: "Заказ поставщику",
  eta: "Срок поставки",
  receive: "Приёмка на склад",
  reserve: "Резерв со склада",
  issue: "Передача в производство",
};

function ActionDialog({
  action,
  lines,
  onClose,
  onDone,
}: {
  action: LineAction;
  lines: LineOut[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const one = lines.length === 1 ? lines[0] : null;
  const title = one ? `«${one.name}»` : `${lines.length} поз.`;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {TITLES[action]}: {title}
          </DialogTitle>
        </DialogHeader>
        {action === "order" && <OrderForm lines={lines} onDone={onDone} />}
        {action === "eta" && <EtaForm lines={lines} onDone={onDone} />}
        {action === "receive" && <ReceiveForm lines={lines} onDone={onDone} />}
        {action === "issue" && <IssueForm lines={lines} onDone={onDone} />}
      </DialogContent>
    </Dialog>
  );
}

function OrderForm({ lines, onDone }: { lines: LineOut[]; onDone: (m: string) => void }) {
  const one = lines.length === 1 ? lines[0] : null;
  const reference = useGetSupplyReference();
  const [supplierId, setSupplierId] = useState(lines.find((l) => l.supplier_id)?.supplier_id ?? "");
  const [newSupplier, setNewSupplier] = useState("");
  const [po, setPo] = useState("");
  const [eta, setEta] = useState(one ? (one.eta ?? one.need_date) : addDaysIso(7));
  const [price, setPrice] = useState(one ? one.price : "");
  const order = useOrderPurchaseLines({ mutation: { onSuccess: (r) => onDone(`Заказ оформлен: ${r.po_number}`) } });
  const createSupplier = useCreateSupplier({
    mutation: {
      onSuccess: (s) => {
        setSupplierId(s.id);
        setNewSupplier("");
        void reference.refetch();
      },
    },
  });
  const late = lines.filter((l) => eta > l.need_date);

  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!supplierId || !eta) {
          toast.error("Укажите поставщика и срок поставки.");
          return;
        }
        order.mutate({
          data: {
            line_ids: lines.map((l) => l.id),
            supplier_id: supplierId,
            eta,
            po_number: po,
            price: one ? price : null,
          },
        });
      }}
    >
      <Field label="Поставщик">
        <OptionSelect
          ariaLabel="Поставщик"
          className="w-full"
          size="default"
          value={supplierId}
          onChange={setSupplierId}
          placeholder="Выберите поставщика"
          options={(reference.data?.suppliers ?? []).map((s) => ({ value: s.id, label: s.name }))}
        />
      </Field>
      <div className="flex gap-2">
        <Input
          value={newSupplier}
          onChange={(e) => setNewSupplier(e.target.value)}
          placeholder="Новый поставщик: ООО «…»"
          aria-label="Новый поставщик"
        />
        <Button
          type="button"
          variant="outline"
          disabled={!newSupplier.trim() || createSupplier.isPending}
          onClick={() => createSupplier.mutate({ data: { name: newSupplier } })}
        >
          Добавить
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="№ заказа поставщику / счёта">
          <Input value={po} onChange={(e) => setPo(e.target.value)} placeholder="пусто — следующий ЗП-…" />
        </Field>
        <Field label="Срок поставки">
          <Input type="date" value={eta} onChange={(e) => setEta(e.target.value)} required />
        </Field>
        {one && (
          <>
            <Field label="Цена за ед., ₽">
              <Input type="number" min="0" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} />
            </Field>
            <Field label="Нужно к">
              <Input value={formatDate(one.need_date)} disabled />
            </Field>
          </>
        )}
      </div>
      <p className={late.length ? "text-sm text-destructive" : "text-sm text-muted-foreground"}>
        {late.length
          ? `Поставка позже потребности: ${late.map((l) => `${l.name} (+${daysBetween(l.need_date, eta)} дн.)`).join(", ")}. Проверьте план заказа.`
          : "Срок укладывается в потребность."}
      </p>
      <DialogFooter>
        <Button type="submit" disabled={order.isPending}>
          Оформить заказ
        </Button>
      </DialogFooter>
    </form>
  );
}

function EtaForm({ lines, onDone }: { lines: LineOut[]; onDone: (m: string) => void }) {
  const one = lines.length === 1 ? lines[0] : null;
  const [eta, setEta] = useState(one?.eta ?? addDaysIso(7));
  const [reason, setReason] = useState("");
  const change = useChangePurchaseLinesEta({ mutation: { onSuccess: () => onDone("Срок поставки изменён") } });
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        change.mutate({ data: { line_ids: lines.map((l) => l.id), eta, reason } });
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Новый срок">
          <Input type="date" value={eta} onChange={(e) => setEta(e.target.value)} required />
        </Field>
        <Field label="Причина переноса">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="письмо поставщика, задержка отгрузки…"
            required
          />
        </Field>
      </div>
      <DialogFooter>
        <Button type="submit" disabled={change.isPending}>
          Сохранить
        </Button>
      </DialogFooter>
    </form>
  );
}

function ReceiveForm({ lines, onDone }: { lines: LineOut[]; onDone: (m: string) => void }) {
  const one = lines.length === 1 ? lines[0] : null;
  const [date, setDate] = useState(todayIso());
  const [place, setPlace] = useState("Склад №1");
  const [qty, setQty] = useState(one ? one.quantity : "");
  const [bad, setBad] = useState("0");
  const [remark, setRemark] = useState("");
  const receive = useReceivePurchaseLines({ mutation: { onSuccess: () => onDone("Принято на склад") } });
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        receive.mutate({
          data: {
            line_ids: lines.map((l) => l.id),
            received_at: date,
            storage_place: place,
            received_qty: one ? qty : null,
            nonconforming: bad || "0",
            remark,
          },
        });
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Дата приёмки">
          <Input type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} required />
        </Field>
        <Field label="Место хранения">
          <Input value={place} onChange={(e) => setPlace(e.target.value)} />
        </Field>
        {one && (
          <Field label={`Принято, ${one.unit} (заказано ${formatQty(one.quantity)})`}>
            <Input type="number" min="0" step="0.001" value={qty} onChange={(e) => setQty(e.target.value)} />
          </Field>
        )}
        <Field label="Входной контроль: не соответствует">
          <Input type="number" min="0" step="0.001" value={bad} onChange={(e) => setBad(e.target.value)} />
        </Field>
      </div>
      <Field label="Замечания">
        <Input value={remark} onChange={(e) => setRemark(e.target.value)} placeholder="сертификаты, упаковка, маркировка" />
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={receive.isPending}>
          Принять
        </Button>
      </DialogFooter>
    </form>
  );
}

function IssueForm({ lines, onDone }: { lines: LineOut[]; onDone: (m: string) => void }) {
  const reference = useGetSupplyReference();
  const centers = useListWorkCenters();
  const [date, setDate] = useState(todayIso());
  const [center, setCenter] = useState("");
  const [employee, setEmployee] = useState("");
  const issue = useIssuePurchaseLines({ mutation: { onSuccess: () => onDone("Передано в производство") } });
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!employee) {
          toast.error("Укажите, кто получил.");
          return;
        }
        issue.mutate({
          data: {
            line_ids: lines.map((l) => l.id),
            issued_at: date,
            issued_to_id: employee,
            work_center_id: center || null,
          },
        });
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Дата">
          <Input type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} required />
        </Field>
        <Field label="Участок">
          <OptionSelect
            ariaLabel="Участок"
            className="w-full"
            size="default"
            value={center}
            onChange={setCenter}
            emptyLabel="ремонтная служба / ТО"
            options={(centers.data ?? []).filter((c) => !c.is_supply).map((c) => ({ value: c.id, label: c.name }))}
          />
        </Field>
      </div>
      <Field label="Получил (мастер, бригадир)">
        <OptionSelect
          ariaLabel="Получил"
          className="w-full"
          size="default"
          value={employee}
          onChange={setEmployee}
          placeholder="Выберите сотрудника"
          options={(reference.data?.employees ?? []).map((e) => ({ value: e.id, label: e.full_name }))}
        />
      </Field>
      <DialogFooter>
        <Button type="submit" disabled={issue.isPending}>
          Передать
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Кнопки действия строки по её серверным `abilities` (`prActBtns` прототипа). */
export function LineActionButtons({
  line,
  run,
  disabled,
}: {
  line: LineOut;
  run: (action: LineAction, lines: LineOut[]) => void;
  disabled?: boolean;
}) {
  const a = line.abilities;
  const button = (action: LineAction, label: string, variant: "default" | "outline" = "outline") => (
    <Button
      key={action}
      size="xs"
      variant={variant}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        run(action, [line]);
      }}
    >
      {label}
    </Button>
  );
  const buttons = [
    a.can_order && button("order", "Заказано", "default"),
    a.can_reserve && button("reserve", "Со склада"),
    a.can_receive && button("receive", "Принять на склад", "default"),
    a.can_change_eta && button("eta", "Срок"),
    a.can_issue && button("issue", "В производство", "default"),
  ].filter(Boolean);
  if (buttons.length) return <div className="flex flex-wrap gap-1">{buttons}</div>;
  if (line.status === "issued") return <span className="text-xs text-muted-foreground">цех {formatDate(line.issued_at)}</span>;
  return null;
}

/** Сроки строки: поставка, склад, цех (`prDates` прототипа). */
export function LineDates({ line }: { line: LineOut }) {
  if (line.status === "draft") return null;
  if (line.status === "issued")
    return (
      <div className="text-xs">
        <div className="text-muted-foreground">склад {formatDate(line.received_at)}</div>
        <div>цех {formatDate(line.issued_at)}</div>
      </div>
    );
  if (line.status === "received" || line.status === "reserved")
    return (
      <div className="text-xs">
        склад {formatDate(line.received_at)}
        {line.received_qty !== null && Number(line.received_qty) < Number(line.quantity) && (
          <div className="text-destructive">
            принято {formatQty(line.received_qty)} из {formatQty(line.quantity)}
          </div>
        )}
      </div>
    );
  if (!line.eta) return <span className="text-xs text-muted-foreground">срок не задан</span>;
  return (
    <div className="text-xs">
      поставка {formatDate(line.eta)}
      {line.status === "ordered" && line.eta < todayIso() && <div className="text-destructive">поставка просрочена</div>}
    </div>
  );
}

/** История позиции «кто, когда, что» (клик по строке реестра). */
export function LineHistoryDialog({ lineId, onClose }: { lineId: string | null; onClose: () => void }) {
  const detail = useGetPurchaseLine(lineId ?? "", { query: { enabled: !!lineId } });
  const line = detail.data;
  return (
    <Dialog open={!!lineId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{line?.name ?? "Позиция"}</DialogTitle>
        </DialogHeader>
        {line && (
          <>
            <p className="text-sm text-muted-foreground">
              {line.order_number || "Склад / ТО"} · {line.requisition_no || "черновик"} · {formatQty(line.quantity)}{" "}
              {line.unit} · {formatRub(line.amount)} · нужно к {formatDate(line.need_date)}
            </p>
            <ul className="flex max-h-96 flex-col gap-2 overflow-auto" data-testid="line-history">
              {line.history.map((entry, index) => (
                <li key={index} className="rounded-md border px-3 py-2">
                  <div className="text-xs text-muted-foreground">
                    {formatDateTime(entry.created_at)} · {entry.author_name}
                  </div>
                  <div className="text-sm">{entry.text}</div>
                </li>
              ))}
            </ul>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
