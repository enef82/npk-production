"use client";

import { useState } from "react";

import { OptionSelect } from "@/components/option-select/option-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LineCategory, LineIn, LineKind, LineOut, SupplyOperationOptionOut } from "@/lib/api/endpoints";

import { LINE_CATEGORY_LABELS, addDaysIso } from "./labels";

const TOOL_CATEGORIES: LineCategory[] = ["fixture", "tool", "consumable"];

/** Черновик позиции заказа: добавить («+ позиция») или изменить. */
export function LineFormDialog({
  open,
  kind,
  line,
  operations,
  pending,
  onClose,
  onSubmit,
}: {
  open: boolean;
  kind: LineKind;
  line: LineOut | null;
  operations: SupplyOperationOptionOut[];
  pending: boolean;
  onClose: () => void;
  onSubmit: (data: LineIn) => void;
}) {
  const [category, setCategory] = useState<LineCategory>(line?.category ?? (kind === "mat" ? "material" : "consumable"));
  const [name, setName] = useState(line?.name ?? "");
  const [quantity, setQuantity] = useState(line?.quantity ?? "1");
  const [unit, setUnit] = useState(line?.unit ?? "шт");
  const [price, setPrice] = useState(line?.price ?? "0");
  const [needDate, setNeedDate] = useState(line?.need_date ?? addDaysIso(7));
  const [operationId, setOperationId] = useState(line?.operation_id ?? "");

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{line ? "Изменить позицию" : "Новая позиция"}</DialogTitle>
        </DialogHeader>
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit({
              kind,
              category: kind === "mat" ? "material" : category,
              name,
              quantity,
              unit,
              price,
              need_date: needDate,
              operation_id: operationId || null,
            });
          }}
        >
          {kind === "tool" && (
            <div className="flex flex-col gap-1.5">
              <Label>Категория</Label>
              <OptionSelect
                ariaLabel="Категория"
                className="w-full"
                size="default"
                value={category}
                onChange={(v) => setCategory(v as LineCategory)}
                options={TOOL_CATEGORIES.map((c) => ({ value: c, label: LINE_CATEGORY_LABELS[c] }))}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="line-name">Наименование</Label>
            <Input
              id="line-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="наименование, марка, ГОСТ"
              required
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="line-qty">Количество</Label>
              <Input
                id="line-qty"
                type="number"
                min="0.001"
                step="0.001"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="line-unit">Ед.</Label>
              <Input id="line-unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="line-price">Цена, ₽</Label>
              <Input
                id="line-price"
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="line-need">Нужно к</Label>
              <Input id="line-need" type="date" value={needDate} onChange={(e) => setNeedDate(e.target.value)} required />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Для операции</Label>
              <OptionSelect
                ariaLabel="Операция"
                className="w-full"
                size="default"
                value={operationId}
                onChange={setOperationId}
                emptyLabel="—"
                options={operations.map((o) => ({ value: o.id, label: o.label }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {line ? "Сохранить" : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
