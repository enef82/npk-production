/**
 * Подписи и цвета экранов аналитики (`renderPerf`, `renderLoad`, `renderPortfolio`,
 * `empPanel` прототипа). Числа приходят с сервера строками Decimal и только
 * показываются: проценты и доли посчитаны на сервере, `null` — «—».
 */
import { num } from "@/lib/production/format";

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const MONTHS_FULL = [
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

/** ISO-дата «2026-11-02» → «02.11» без перевода часовых поясов. */
export function dayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

/** Неделя «02.11–06.11» (пн–пт). */
export function weekLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const friday = new Date(Date.UTC(y, m - 1, d + 4));
  const fd = `${String(friday.getUTCDate()).padStart(2, "0")}.${String(friday.getUTCMonth() + 1).padStart(2, "0")}`;
  return `${dayMonth(iso)}–${fd}`;
}

/** «2026-11-01» → «ноя 26» (`monLbl`). */
export function monthLabel(iso: string): string {
  const [y, m] = iso.split("-");
  return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`;
}

export function monthName(iso: string): string {
  return MONTHS_FULL[Number(iso.split("-")[1]) - 1];
}

/** «75%» / «—». */
export function pctText(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(num(value))}%`;
}

/** «1,88» / «—». */
export function ratioText(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return num(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Тысячи рублей: «1 234 тыс». */
export function kRub(value: string | number | null | undefined): string {
  return `${Math.round(num(value) / 1000).toLocaleString("ru-RU")} тыс`;
}

/** Ячейка % выполнения плана (`renderPerf`): ≥95 — зелёная, ≥80 — жёлтая, ниже — красная. */
export function planColor(pct: string | null | undefined): string {
  if (pct === null || pct === undefined) return "#f4f5f7";
  const p = num(pct);
  return p >= 95 ? "#cfe3d6" : p >= 80 ? "#f7e7b8" : "#f3c0c0";
}

/** Загрузка 10 недель (`renderLoad`): > 100 % — перегрузка. */
export function loadColor(ratio: number): string {
  return ratio > 1 ? "#f3b0b0" : ratio > 0.85 ? "#f7d79e" : ratio > 0.5 ? "#cfe3d6" : ratio > 0 ? "#e8f2ec" : "#f4f5f7";
}

/** Загрузка по месяцам портфеля (`heat`). */
export function heatColor(ratio: number): string {
  return ratio > 1 ? "#f3b0b0" : ratio > 0.9 ? "#f7d79e" : ratio > 0.6 ? "#cfe3d6" : ratio > 0 ? "#e8f2ec" : "#f4f5f7";
}

/** Цвет текста показателя по порогам «хорошо / предупреждение». */
export function toneClass(value: string | null | undefined, good: number, warn: number): string {
  if (value === null || value === undefined) return "";
  const v = num(value);
  return v >= good ? "text-emerald-700" : v >= warn ? "text-amber-700" : "text-destructive";
}
