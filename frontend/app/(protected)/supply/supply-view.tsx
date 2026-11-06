"use client";

import { useMemo, useState } from "react";
import { Plus } from "lucide-react";

import { OptionSelect } from "@/components/option-select/option-select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  LINE_CATEGORY_LABELS,
  LINE_STATUS_LABELS,
  LateBadge,
  LineStatusBadge,
  formatQty,
  formatRub,
} from "@/components/supply/labels";
import {
  LineActionButtons,
  LineDates,
  LineHistoryDialog,
  useLineActions,
  type LineAction,
} from "@/components/supply/line-actions";
import { NewRequisitionDialog } from "@/components/supply/new-requisition-dialog";
import {
  useGetSupplyDashboard,
  useListPurchaseLines,
  useListSupplyOrders,
  type LineCategory,
  type LineKind,
  type LineOut,
  type ListPurchaseLinesParams,
} from "@/lib/api/endpoints";
import { formatDate, formatDateTime } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

type Filters = {
  status: string;
  category: string;
  kind: string;
  orderId: string;
  late: boolean;
  requisition: string;
  search: string;
};

const INITIAL: Filters = {
  status: "active",
  category: "",
  kind: "",
  orderId: "",
  late: false,
  requisition: "",
  search: "",
};

const STATUS_OPTIONS = [
  { value: "active", label: "Все, кроме выданных в цех" },
  { value: "all", label: "Все" },
  { value: "store", label: "На складе, к выдаче" },
  ...(["sent", "ordered", "received", "reserved", "issued"] as const).map((s) => ({
    value: s,
    label: LINE_STATUS_LABELS[s],
  })),
];

const WAREHOUSE = "warehouse";

/** Групповое действие доступно, если оно разрешено каждой отмеченной строке. */
const BULK: { action: LineAction; label: string; allowed: (l: LineOut) => boolean }[] = [
  { action: "order", label: "Заказано", allowed: (l) => l.abilities.can_order },
  { action: "reserve", label: "Со склада", allowed: (l) => l.abilities.can_reserve },
  { action: "eta", label: "Срок", allowed: (l) => l.abilities.can_change_eta },
  { action: "receive", label: "Принять на склад", allowed: (l) => l.abilities.can_receive },
  { action: "issue", label: "В производство", allowed: (l) => l.abilities.can_issue },
];

/** Экран «Закупки и склад» (`renderProc` прототипа). */
export function SupplyView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const dashboard = useGetSupplyDashboard();
  const orders = useListSupplyOrders();
  const actions = useLineActions(() => setPicked(new Set()));

  const params: ListPurchaseLinesParams = {
    status: filters.status === "all" ? "" : filters.status,
    category: (filters.category || undefined) as LineCategory | undefined,
    kind: (filters.kind || undefined) as LineKind | undefined,
    order_id: filters.orderId && filters.orderId !== WAREHOUSE ? filters.orderId : undefined,
    warehouse_only: filters.orderId === WAREHOUSE || undefined,
    late_only: filters.late || undefined,
    requisition_no: filters.requisition || undefined,
    search: filters.search || undefined,
  };
  const query = useListPurchaseLines(params, { query: { placeholderData: (prev) => prev } });
  const lines = useMemo(() => query.data ?? [], [query.data]);
  const selected = lines.filter((l) => picked.has(l.id));

  const set = (change: Partial<Filters>) => {
    setFilters((prev) => ({ ...prev, ...change }));
    setPicked(new Set());
  };
  const counts = dashboard.data?.counts;
  const kpis = counts
    ? [
        { key: "sent", value: String(counts.sent), label: "к заказу (снабжение)", apply: { status: "sent", late: false } },
        { key: "ordered", value: String(counts.ordered), label: "заказано, ждём поставку", apply: { status: "ordered", late: false } },
        {
          key: "store",
          value: String(counts.received + counts.reserved),
          label: "на складе, к выдаче в цех",
          apply: { status: "store", late: false },
        },
        { key: "late", value: String(counts.late), label: "опаздывают к потребности", apply: { status: "active", late: true }, bad: counts.late > 0 },
        { key: "sum", value: formatRub(counts.active_amount), label: "в работе, сумма", apply: { ...INITIAL } },
      ]
    : [];

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Закупки и склад</h1>
        <Button size="sm" disabled={!dashboard.data?.abilities.can_request} onClick={() => setNewOpen(true)}>
          <Plus className="size-4" aria-hidden />
          Заявка на закупку
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {kpis.map((k) => (
          <button
            key={k.key}
            type="button"
            className="flex flex-col items-start rounded-lg border px-4 py-3 text-left hover:bg-muted"
            onClick={() => set({ ...k.apply, requisition: "" })}
          >
            <b className={cn("text-xl", k.bad && "text-destructive")}>{k.value}</b>
            <span className="text-xs text-muted-foreground">{k.label}</span>
          </button>
        ))}
      </div>

      <section className="rounded-lg border p-3">
        <div className="mb-2 flex flex-wrap items-baseline gap-2">
          <h2 className="font-semibold">Заявки на закупку</h2>
          <span className="text-xs text-muted-foreground">
            заказ и срок — снабжение; приёмка и выдача в цех — начальник склада или начальник производства
          </span>
        </div>
        <div className="max-h-60 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Заявка</TableHead>
                <TableHead>Заказ</TableHead>
                <TableHead>Передал</TableHead>
                <TableHead>Дата</TableHead>
                <TableHead className="text-right">Позиций</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead>Выполнение</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(dashboard.data?.requisitions ?? []).map((r) => {
                const waiting = r.lines - r.ordered - r.in_store - r.issued;
                return (
                  <TableRow
                    key={r.number}
                    className={cn("cursor-pointer", filters.requisition === r.number && "bg-primary/5")}
                    onClick={() =>
                      set(
                        filters.requisition === r.number
                          ? { requisition: "" }
                          : { requisition: r.number, status: "all", late: false },
                      )
                    }
                  >
                    <TableCell className="font-medium">{r.number}</TableCell>
                    <TableCell>{r.order_number || "Склад / ТО"}</TableCell>
                    <TableCell>{r.sent_by_name || "—"}</TableCell>
                    <TableCell>{formatDateTime(r.sent_at)}</TableCell>
                    <TableCell className="text-right">{r.lines}</TableCell>
                    <TableCell className="text-right">{formatRub(r.amount)}</TableCell>
                    <TableCell className="min-w-56">
                      <div className="flex h-2 overflow-hidden rounded bg-muted">
                        <i className="bg-emerald-600" style={{ width: `${(r.issued / r.lines) * 100}%` }} />
                        <i className="bg-emerald-300" style={{ width: `${(r.in_store / r.lines) * 100}%` }} />
                        <i className="bg-amber-300" style={{ width: `${(r.ordered / r.lines) * 100}%` }} />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        заказано {r.ordered} · на складе {r.in_store} · в цехе {r.issued} · ждут заказа {waiting}
                      </span>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="flex flex-col gap-2 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-2 font-semibold">Позиции</h2>
          <OptionSelect
            ariaLabel="Статус"
            className="w-60"
            value={filters.status}
            onChange={(status) => set({ status })}
            options={STATUS_OPTIONS}
          />
          <OptionSelect
            ariaLabel="Заказ"
            className="w-56"
            value={filters.orderId}
            onChange={(orderId) => set({ orderId })}
            emptyLabel="Все заказы"
            options={[
              { value: WAREHOUSE, label: "Склад / ТО" },
              ...(orders.data ?? []).map((o) => ({ value: o.id, label: o.label })),
            ]}
          />
          <OptionSelect
            ariaLabel="Вид"
            className="w-44"
            value={filters.kind}
            onChange={(kind) => set({ kind })}
            emptyLabel="Все виды"
            options={[
              { value: "mat", label: "Материалы" },
              { value: "tool", label: "Оснастка и расходники" },
            ]}
          />
          <OptionSelect
            ariaLabel="Категория"
            className="w-40"
            value={filters.category}
            onChange={(category) => set({ category })}
            emptyLabel="Все категории"
            options={(Object.keys(LINE_CATEGORY_LABELS) as LineCategory[]).map((c) => ({
              value: c,
              label: LINE_CATEGORY_LABELS[c],
            }))}
          />
          <label className="flex items-center gap-1.5 text-sm">
            <Checkbox checked={filters.late} onCheckedChange={(on) => set({ late: !!on })} aria-label="Только опаздывающие" />
            только опаздывающие
          </label>
          <Input
            className="h-8 w-56"
            value={filters.search}
            onChange={(e) => set({ search: e.target.value })}
            placeholder="Поиск: позиция, поставщик, №…"
            aria-label="Поиск по позициям"
          />
          {filters.requisition && (
            <Button size="xs" variant="secondary" onClick={() => set({ requisition: "" })}>
              заявка {filters.requisition} ✕
            </Button>
          )}
          <span className="text-xs text-muted-foreground">{lines.length} строк</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">
            {selected.length
              ? `Отмечено ${selected.length}:`
              : "Отметьте строки для группового действия — доступно то, что разрешено каждой отмеченной строке"}
          </span>
          {BULK.map((b) => (
            <Button
              key={b.action}
              size="xs"
              variant="outline"
              disabled={!selected.length || !selected.every(b.allowed) || actions.pending}
              onClick={() => actions.run(b.action, selected)}
            >
              {b.label}
            </Button>
          ))}
        </div>

        <div className="overflow-x-auto">
          <Table data-testid="supply-lines">
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Заказ</TableHead>
                <TableHead>Позиция</TableHead>
                <TableHead className="text-right">Кол-во</TableHead>
                <TableHead className="text-right">Сумма</TableHead>
                <TableHead>Нужно к</TableHead>
                <TableHead>Статус · заявка</TableHead>
                <TableHead>Поставщик · заказ</TableHead>
                <TableHead>Сроки</TableHead>
                <TableHead className="text-right">Откл.</TableHead>
                <TableHead>Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading && (
                <TableRow>
                  <TableCell colSpan={11} className="text-muted-foreground">
                    Загрузка…
                  </TableCell>
                </TableRow>
              )}
              {!query.isLoading && lines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={11} className="text-muted-foreground">
                    Позиций нет.
                  </TableCell>
                </TableRow>
              )}
              {lines.map((line) => (
                <TableRow
                  key={line.id}
                  className={cn("cursor-pointer", line.late_days > 0 && "bg-destructive/5")}
                  onClick={() => setHistoryId(line.id)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {line.status !== "issued" && (
                      <Checkbox
                        aria-label={`Отметить ${line.name}`}
                        checked={picked.has(line.id)}
                        onCheckedChange={(on) =>
                          setPicked((prev) => {
                            const next = new Set(prev);
                            if (on) next.add(line.id);
                            else next.delete(line.id);
                            return next;
                          })
                        }
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    {line.order_number ? (
                      <>
                        <div className="font-medium">{line.order_number}</div>
                        <div className="text-xs text-muted-foreground">{line.customer_name}</div>
                      </>
                    ) : (
                      <span className="text-muted-foreground">Склад / ТО</span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-64 whitespace-normal">
                    {line.name} <span className="text-xs text-muted-foreground">· {LINE_CATEGORY_LABELS[line.category]}</span>
                    <div className="text-xs text-muted-foreground">запросил {line.created_by_name}</div>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {formatQty(line.quantity)} {line.unit}
                  </TableCell>
                  <TableCell className="text-right">{formatRub(line.amount)}</TableCell>
                  <TableCell>{formatDate(line.need_date)}</TableCell>
                  <TableCell>
                    <LineStatusBadge status={line.status} />
                    <div className="text-xs text-muted-foreground">{line.requisition_no}</div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {line.supplier_name}
                    {line.po_number && <div>{line.po_number}</div>}
                  </TableCell>
                  <TableCell>
                    <LineDates line={line} />
                  </TableCell>
                  <TableCell className="text-right">
                    {["received", "reserved", "issued"].includes(line.status) ? (
                      <span className="text-emerald-700">✓</span>
                    ) : line.late_days > 0 ? (
                      <LateBadge days={line.late_days} />
                    ) : line.eta ? (
                      <span className="text-xs text-emerald-700">в срок</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <LineActionButtons line={line} run={actions.run} disabled={actions.pending} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <p className="text-xs text-muted-foreground">
          Клик по строке — история позиции. Отклонение — на сколько дней поставка позже потребности по плану заказа.
        </p>
      </section>

      {actions.element}
      <LineHistoryDialog lineId={historyId} onClose={() => setHistoryId(null)} />
      <NewRequisitionDialog open={newOpen} onClose={() => setNewOpen(false)} />
    </div>
  );
}
