"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";

import { OptionSelect } from "@/components/option-select/option-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateRequisition, useListSupplyOrders, type LineCategory } from "@/lib/api/endpoints";

import { LINE_CATEGORY_LABELS, addDaysIso } from "./labels";
import { useInvalidateSupply } from "./line-actions";

type Row = { category: LineCategory; name: string; quantity: string; unit: string; price: string; need: string };

const CATEGORIES: LineCategory[] = ["material", "fixture", "tool", "consumable"];

const newRow = (need?: string): Row => ({
  category: "material",
  name: "",
  quantity: "1",
  unit: "шт",
  price: "0",
  need: need ?? addDaysIso(7),
});

/**
 * Новая заявка на закупку (`newReqDialog` прототипа): для заказа в работе или
 * «Склад / ТО / общие нужды»; позиции создаются и сразу передаются в закупку.
 */
export function NewRequisitionDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const orders = useListSupplyOrders({ query: { enabled: open } });
  const invalidate = useInvalidateSupply();
  const [orderId, setOrderId] = useState("");
  const [rows, setRows] = useState<Row[]>([newRow()]);
  const create = useCreateRequisition({
    mutation: {
      onSuccess: (r) => {
        toast.success(`Создана заявка ${r.requisition_no} — передана в отдел закупок`);
        setRows([newRow()]);
        setOrderId("");
        void invalidate();
        onClose();
      },
    },
  });

  const patch = (index: number, change: Partial<Row>) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...change } : row)));

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Новая заявка на закупку</DialogTitle>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const ok = rows.filter((r) => r.name.trim() && Number(r.quantity) > 0);
            if (!ok.length) {
              toast.error("Добавьте хотя бы одну позицию с наименованием и количеством.");
              return;
            }
            create.mutate({
              data: {
                order_id: orderId || null,
                lines: ok.map((r) => ({
                  kind: r.category === "material" ? "mat" : "tool",
                  category: r.category,
                  name: r.name,
                  quantity: r.quantity,
                  unit: r.unit,
                  price: r.price || "0",
                  need_date: r.need,
                })),
              },
            });
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label>Для чего</Label>
            <OptionSelect
              ariaLabel="Для чего"
              className="w-full"
              size="default"
              value={orderId}
              onChange={setOrderId}
              emptyLabel="Склад / ТО / общие нужды"
              options={(orders.data ?? []).map((o) => ({ value: o.id, label: o.label }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            {rows.map((row, index) => (
              <div key={index} className="grid grid-cols-[9rem_1fr_6rem_4rem_6rem_9rem_2rem] items-center gap-2">
                <OptionSelect
                  ariaLabel="Категория"
                  className="w-full"
                  value={row.category}
                  onChange={(v) => patch(index, { category: v as LineCategory })}
                  options={CATEGORIES.map((c) => ({ value: c, label: LINE_CATEGORY_LABELS[c] }))}
                />
                <Input
                  aria-label="Наименование"
                  value={row.name}
                  onChange={(e) => patch(index, { name: e.target.value })}
                  placeholder="наименование, марка, ГОСТ"
                />
                <Input
                  aria-label="Количество"
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={row.quantity}
                  onChange={(e) => patch(index, { quantity: e.target.value })}
                />
                <Input aria-label="Ед." value={row.unit} onChange={(e) => patch(index, { unit: e.target.value })} />
                <Input
                  aria-label="Цена"
                  type="number"
                  min="0"
                  step="0.01"
                  value={row.price}
                  onChange={(e) => patch(index, { price: e.target.value })}
                />
                <Input
                  aria-label="Нужно к"
                  type="date"
                  value={row.need}
                  onChange={(e) => patch(index, { need: e.target.value })}
                />
                <Button
                  type="button"
                  size="icon-xs"
                  variant="ghost"
                  aria-label="Удалить строку"
                  onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                >
                  <X />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="w-fit"
              onClick={() => setRows((prev) => [...prev, newRow(prev[prev.length - 1]?.need)])}
            >
              <Plus className="size-4" aria-hidden />
              строка
            </Button>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              Создать и передать в закупку
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
