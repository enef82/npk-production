"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type Option = { value: string; label: string };

/** Пустое значение base-ui Select не принимает — подставляем служебное. */
const EMPTY = "__empty";

/**
 * Выпадающий список из пар «значение — подпись» поверх shadcn/base-ui `Select`.
 * Пустая строка `value` — «ничего не выбрано» (подпись `emptyLabel`); если `emptyLabel`
 * не задан, пустой пункт в списке не показывается.
 */
export function OptionSelect({
  value,
  onChange,
  options,
  emptyLabel,
  placeholder,
  ariaLabel,
  className,
  size = "sm",
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  emptyLabel?: string;
  placeholder?: string;
  ariaLabel: string;
  className?: string;
  size?: "sm" | "default";
  disabled?: boolean;
}) {
  const labels = new Map(options.map((o) => [o.value, o.label]));
  return (
    <Select
      value={value === "" ? EMPTY : value}
      onValueChange={(next) => onChange(next === EMPTY || next === null ? "" : String(next))}
      disabled={disabled}
    >
      <SelectTrigger size={size} className={cn("w-48", className)} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder ?? emptyLabel ?? "—"}>
          {(current: string | null) =>
            current && current !== EMPTY ? (labels.get(current) ?? current) : (emptyLabel ?? placeholder ?? "—")
          }
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {emptyLabel !== undefined && <SelectItem value={EMPTY}>{emptyLabel}</SelectItem>}
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
