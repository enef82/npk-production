function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function isoDay(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return isoDay(new Date(y, m - 1, d + n));
}

export function yesterday(): string {
  return addDays(isoDay(new Date()), -1);
}

export function isWeekend(day: string): boolean {
  const [y, m, d] = day.split("-").map(Number);
  const w = new Date(y, m - 1, d).getDay();
  return w === 0 || w === 6;
}

/** Последний рабочий день не позже `day`. */
export function lastWorkday(day: string): string {
  let d = day;
  while (isWeekend(d)) d = addDays(d, -1);
  return d;
}

export function daysBetween(from: string, to: string): string[] {
  const out: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) out.push(d);
  return out;
}

/** Первое число месяца `back` месяцев назад. */
export function monthStartBack(back: number): string {
  const now = new Date();
  return isoDay(new Date(now.getFullYear(), now.getMonth() - back, 1));
}

const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

export function monthShort(day: string): string {
  return `${MONTHS[Number(day.slice(5, 7)) - 1]} ${day.slice(2, 4)}`;
}

/** Рабочая смена 8:00–17:00 без обеда 12:00–13:00 — получасовые слоты 16..33 кроме 24, 25. */
export function isWorkSlot(slot: number): boolean {
  return slot >= 16 && slot < 34 && !(slot >= 24 && slot < 26);
}

/** Текущее время, округлённое вниз до получаса, для `datetime-local`. */
export function nowHalfHourLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() < 30 ? 0 : 30, 0, 0);
  return `${isoDay(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
