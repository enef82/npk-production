/**
 * Деньги и количества приходят с сервера строками Decimal. Здесь они только
 * показываются — округление при выводе (§2.2), арифметики над деньгами на клиенте нет,
 * кроме сумм для KPI доски, где точность до рубля не важна.
 */

const rubFormatter = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const qtyFormatter = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });
const hoursFormatter = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

export function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

/** «1 234 567 ₽» */
export function rub(value: string | number | null | undefined): string {
  return `${rubFormatter.format(num(value))} ₽`;
}

/** «1,2 млн ₽» / «850 тыс. ₽» — для KPI и карточек доски, как `krub()` прототипа. */
export function krub(value: string | number | null | undefined): string {
  const n = num(value);
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} млн ₽`;
  if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000).toLocaleString("ru-RU")} тыс. ₽`;
  return rub(n);
}

export function qty(value: string | number | null | undefined): string {
  return qtyFormatter.format(num(value));
}

export function hours(value: string | number | null | undefined): string {
  return hoursFormatter.format(num(value));
}

/** Инициалы для аватара: «Морозов Д.В.» → «МД». */
export function initials(name: string): string {
  const parts = name.replace(/\./g, " ").split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "");
}
