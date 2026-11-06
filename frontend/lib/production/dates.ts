/**
 * Рабочие дни (пн–пт, без праздников — `docs/spec/00-prilozhenie-proizvodstvo.md` §2.1).
 * Та же нумерация, что у `core.common.scheduling.work_index` на сервере: выходной
 * относится к следующему рабочему дню. Даты — строки ISO `YYYY-MM-DD`, арифметика в UTC,
 * чтобы часовой пояс браузера не сдвигал день.
 */

const DAY_MS = 86_400_000;
// Понедельник — опорная точка нумерации (на сервере своя, но разность индексов совпадает).
const EPOCH = Date.UTC(2000, 0, 3);

export function parseIso(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

export function toIso(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function todayIso(): string {
  const now = new Date();
  return toIso(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
}

/** 0 — понедельник … 6 — воскресенье. */
export function weekday(day: string): number {
  return (new Date(parseIso(day)).getUTCDay() + 6) % 7;
}

export function nextWorkingDay(day: string): string {
  let ms = parseIso(day);
  while ((new Date(ms).getUTCDay() + 6) % 7 >= 5) ms += DAY_MS;
  return toIso(ms);
}

export function workIndex(day: string): number {
  const days = Math.round((parseIso(nextWorkingDay(day)) - EPOCH) / DAY_MS);
  return Math.floor(days / 7) * 5 + (days % 7);
}

export function fromWorkIndex(index: number): string {
  const weeks = Math.floor(index / 5);
  const rest = index - weeks * 5;
  return toIso(EPOCH + (weeks * 7 + rest) * DAY_MS);
}

export function addWorkingDays(day: string, days: number): string {
  return fromWorkIndex(workIndex(day) + days);
}

export function workingDaysBetween(start: string, end: string): number {
  return workIndex(end) - workIndex(start);
}

const shortDate = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** «05.11» — как `fd()` прототипа. */
export function fd(day: string | null | undefined): string {
  return day ? shortDate.format(parseIso(day)) : "—";
}

/** «5 нояб. 2026 г.» — как `fdl()` прототипа. */
export function fdl(day: string | null | undefined): string {
  return day ? longDate.format(parseIso(day)) : "—";
}

export const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
