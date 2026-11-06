"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { toast } from "sonner";

import { compareDecimal, parseDecimalInput, subtractDecimal, sumDecimals } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  saveTimesheetDay,
  useGetTimesheetDay,
  useListTimeCodes,
  useListTimesheetOrderOperations,
  useListTimesheetOrders,
  type DayOut,
  type TimeCodeOut,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";

import { TARGET_LABELS, dayLabel, hours, objectLabel } from "./labels";

type Row = {
  key: number;
  time_code: string;
  target: string;
  order_id: string | null;
  operation_id: string | null;
  hours: string;
};

const FIXED_TARGETS = ["overhead", "repair", "training", "idle"] as const;
let rowSeq = 0;

function newRow(partial: Partial<Row>): Row {
  rowSeq += 1;
  return { key: rowSeq, time_code: "Я", target: "overhead", order_id: null, operation_id: null, hours: "8", ...partial };
}

/** Строки «по плану»: 8 ч поровну на плановые операции участка (шаг 0,5 ч), остаток — накладные.
 * Считается в получасах целыми числами — без дробной арифметики. */
function planRows(day: DayOut): Row[] {
  const n = day.planned.length;
  const per = Math.floor(16 / n);
  const rest = 16 - per * n;
  const rows = day.planned.map((p) =>
    newRow({ target: "order", order_id: p.order_id, operation_id: p.operation_id, hours: String(per / 2) }),
  );
  if (rest > 0) rows.push(newRow({ target: "overhead", hours: String(rest / 2) }));
  return rows;
}

export function DayDialog({
  employeeId,
  day,
  onClose,
  onSaved,
}: {
  employeeId: string;
  day: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const query = useGetTimesheetDay(employeeId, day);
  const codes = useListTimeCodes();

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-4xl" data-testid="day-dialog">
        {query.data && codes.data ? (
          <DayEditor
            key={`${employeeId}-${day}`}
            data={query.data}
            codes={codes.data}
            onClose={onClose}
            onSaved={onSaved}
          />
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Разноска дня · {dayLabel(day)}</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">Загрузка…</p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DayEditor({
  data,
  codes,
  onClose,
  onSaved,
}: {
  data: DayOut;
  codes: TimeCodeOut[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [rows, setRows] = useState<Row[]>(() =>
    data.rows.map((r) =>
      newRow({
        time_code: r.time_code,
        target: r.target,
        order_id: r.order_id,
        operation_id: r.operation_id,
        hours: r.hours,
      }),
    ),
  );
  const [saving, setSaving] = useState(false);
  const orders = useListTimesheetOrders({ query: { enabled: data.can_edit } });
  const codeOf = new Map(codes.map((c) => [c.code, c]));
  // Заказ строки может быть уже не в работе — подпись берём из ответа дня.
  const knownOrders = new Map<string, string>(orders.data?.map((o) => [o.order_id, o.label]) ?? []);
  for (const r of data.rows) if (r.order_id && !knownOrders.has(r.order_id)) knownOrders.set(r.order_id, r.order_label);

  const total = sumDecimals(rows.map((r) => parseDecimalInput(r.hours) ?? "0"));
  const update = (key: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function save() {
    if (rows.some((r) => {
      const h = parseDecimalInput(r.hours);
      return h === null || compareDecimal(h, "0") <= 0;
    })) {
      toast.error("У каждой строки должны быть часы больше нуля.");
      return;
    }
    if (compareDecimal(total, "24") > 0) {
      toast.error("Больше 24 часов в день.");
      return;
    }
    if (rows.some((r) => r.target === "order" && !r.order_id)) {
      toast.error("Выберите заказ в строке разноски.");
      return;
    }
    setSaving(true);
    try {
      await saveTimesheetDay(data.employee_id, data.date, {
        rows: rows.map((r) => ({
          time_code: r.time_code,
          hours: parseDecimalInput(r.hours) ?? "0",
          target: r.target,
          order_id: r.target === "order" ? r.order_id : null,
          operation_id: r.target === "order" ? r.operation_id : null,
        })),
      });
      toast.success("Разноска дня сохранена");
      await onSaved();
      onClose();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось сохранить разноску.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {data.full_name} · {dayLabel(data.date)}
        </DialogTitle>
        <DialogDescription>
          {data.position} · {data.department_name}
        </DialogDescription>
      </DialogHeader>

      {!data.can_edit && (
        <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
          Правка закрыта: период не в статусе «Заполняется» или у вас нет прав на это подразделение.
        </p>
      )}

      {data.can_edit ? (
        <div className="flex flex-col gap-2">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="w-52 py-1 text-left font-medium">Вид времени</th>
                <th className="text-left font-medium">Заказ / объект</th>
                <th className="text-left font-medium">Операция</th>
                <th className="w-24 text-right font-medium">Часы</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const allocatable = codeOf.get(row.time_code)?.is_allocatable ?? true;
                return (
                  <tr key={row.key} className="align-top" data-testid="day-row">
                    <td className="py-1 pr-2">
                      <NativeSelect
                        aria-label="Вид времени"
                        value={row.time_code}
                        onChange={(e) => {
                          const code = codeOf.get(e.target.value);
                          update(
                            row.key,
                            code && !code.is_allocatable
                              ? { time_code: e.target.value, target: "", order_id: null, operation_id: null }
                              : { time_code: e.target.value, target: row.target || "overhead" },
                          );
                        }}
                      >
                        {codes.map((c) => (
                          <option key={c.code} value={c.code}>
                            {c.code} — {c.name}
                          </option>
                        ))}
                      </NativeSelect>
                    </td>
                    <td className="py-1 pr-2">
                      {allocatable ? (
                        <NativeSelect
                          aria-label="Объект разноски"
                          value={row.target === "order" ? `order:${row.order_id ?? ""}` : row.target}
                          onChange={(e) => {
                            const v = e.target.value;
                            update(
                              row.key,
                              v.startsWith("order:")
                                ? { target: "order", order_id: v.slice(6) || null, operation_id: null }
                                : { target: v, order_id: null, operation_id: null },
                            );
                          }}
                        >
                          {row.target === "order" && !row.order_id && <option value="order:">— выберите заказ —</option>}
                          {[...knownOrders].map(([id, label]) => (
                            <option key={id} value={`order:${id}`}>
                              {label}
                            </option>
                          ))}
                          {FIXED_TARGETS.map((t) => (
                            <option key={t} value={t}>
                              {TARGET_LABELS[t]}
                            </option>
                          ))}
                        </NativeSelect>
                      ) : (
                        <span className="text-xs text-muted-foreground">без разноски</span>
                      )}
                    </td>
                    <td className="py-1 pr-2">
                      {row.target === "order" && row.order_id && (
                        <OperationSelect
                          orderId={row.order_id}
                          value={row.operation_id}
                          workCenterId={data.work_center_id}
                          onChange={(operationId) => update(row.key, { operation_id: operationId })}
                        />
                      )}
                    </td>
                    <td className="py-1">
                      <Input
                        aria-label="Часы"
                        inputMode="decimal"
                        className="text-right"
                        value={row.hours}
                        onChange={(e) => update(row.key, { hours: e.target.value })}
                      />
                    </td>
                    <td className="py-1 pl-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Удалить строку"
                        onClick={() => setRows((prev) => prev.filter((r) => r.key !== row.key))}
                      >
                        <X />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const rest = compareDecimal(total, "8") < 0 ? subtractDecimal("8", total) : "8";
                const plan = data.planned[0];
                setRows((prev) => [
                  ...prev,
                  newRow(
                    plan
                      ? { target: "order", order_id: plan.order_id, operation_id: plan.operation_id, hours: rest }
                      : { hours: rest },
                  ),
                ]);
              }}
            >
              + строка
            </Button>
            {data.planned.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setRows(planRows(data))}>
                По плану: {data.planned.map((p) => p.label).join(", ")}
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setRows([newRow({ target: "overhead" })])}>
              8 ч накладные
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRows([newRow({ target: "idle" })])}>
              8 ч простой
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRows([newRow({ time_code: "К", target: "overhead" })])}>
              Командировка
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRows([newRow({ time_code: "ПР", target: "" })])}>
              Прогул
            </Button>
          </div>
          {data.planned.length === 0 && (
            <p className="text-xs text-muted-foreground">Плановых операций участка на этот день нет.</p>
          )}
        </div>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.id} className="border-t">
                <td className="py-1">
                  {r.time_code} — {r.time_code_name}
                </td>
                <td>{r.target ? objectLabel(r.target, r.order_label) : "без разноски"}</td>
                <td className="text-muted-foreground">{r.operation_label}</td>
                <td className="text-right tabular-nums">{hours(r.hours)} ч</td>
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td className="py-1 text-muted-foreground">Разноски нет.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <div className="flex items-center justify-between border-t pt-2 text-sm">
        <span>Итого за день</span>
        <b data-testid="day-total">{hours(total)} ч</b>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          {data.can_edit ? "Отмена" : "Закрыть"}
        </Button>
        {data.can_edit && (
          <Button disabled={saving} onClick={save}>
            Сохранить
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

function OperationSelect({
  orderId,
  value,
  workCenterId,
  onChange,
}: {
  orderId: string;
  value: string | null;
  workCenterId: string | null;
  onChange: (operationId: string | null) => void;
}) {
  const operations = useListTimesheetOrderOperations(orderId);
  return (
    <NativeSelect aria-label="Операция" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">—</option>
      {operations.data?.map((op) => (
        <option key={op.operation_id} value={op.operation_id}>
          {op.label}
          {op.work_center_id === workCenterId ? " ★" : ""}
        </option>
      ))}
    </NativeSelect>
  );
}
