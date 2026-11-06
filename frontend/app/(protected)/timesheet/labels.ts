import type { PeriodEventKind, PeriodStatus } from "@/lib/api/endpoints";

export const PERIOD_STATUS_LABELS: Record<PeriodStatus, string> = {
  draft: "Заполняется",
  on_review: "На согласовании",
  approved: "Утверждён",
  sent: "Передан в 1С",
  closed: "Закрыт",
  reopened: "Открыт для корректировки",
};

export const PERIOD_STATUS_TONE: Record<PeriodStatus, string> = {
  draft: "bg-muted text-foreground",
  on_review: "bg-amber-100 text-amber-900",
  approved: "bg-blue-100 text-blue-900",
  sent: "bg-emerald-100 text-emerald-900",
  closed: "bg-emerald-100 text-emerald-900",
  reopened: "bg-red-100 text-red-900",
};

export const PERIOD_EVENT_LABELS: Record<PeriodEventKind, string> = {
  submitted: "Подан на согласование",
  manager_confirmed: "Часы по заказам подтверждены",
  returned: "Возвращён на доработку",
  approved: "Утверждён",
  sent: "Передан в 1С",
  closed: "Закрыт",
  reopened: "Открыт для корректировки",
};

/** Объекты разноски без заказа (`AllocationTarget`). */
export const TARGET_LABELS: Record<string, string> = {
  order: "Заказ",
  overhead: "Накладные подразделения",
  repair: "Ремонт и ТО оборудования",
  training: "Обучение и аттестация",
  idle: "Простой",
};

export function objectLabel(target: string, orderLabel: string): string {
  if (target === "order") return orderLabel || "Заказ";
  return TARGET_LABELS[target] ?? target;
}

const MONTHS = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
];

export const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

/** «2026-10-01» → «Октябрь 2026». */
export function monthTitle(month: string): string {
  const [y, m] = month.split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Первые числа: текущий месяц и `back` предыдущих, от новых к старым. */
export function recentMonths(back: number): string[] {
  const now = new Date();
  return Array.from({ length: back + 1 }, (_, i) => iso(new Date(now.getFullYear(), now.getMonth() - i, 1)));
}

export function weekdayOf(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return WEEKDAYS[new Date(y, m - 1, d).getDay()];
}

export function dayLabel(day: string): string {
  const [y, m, d] = day.split("-");
  return `${d}.${m}.${y}, ${weekdayOf(day)}`;
}

/** Часы без лишних нулей: «8.00» → «8», «7.50» → «7,5». */
export function hours(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const [int, frac = ""] = value.split(".");
  const trimmed = frac.replace(/0+$/, "");
  return trimmed ? `${int},${trimmed}` : int;
}
