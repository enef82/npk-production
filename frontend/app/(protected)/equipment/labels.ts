import type { EquipmentStatus, MaintenanceState, RepairKind, RepairStatus } from "@/lib/api/endpoints";

export const EQUIPMENT_STATUS_LABELS: Record<EquipmentStatus, string> = {
  run: "Работает",
  idle: "Простаивает",
  to: "На ТО",
  repair: "В ремонте",
};

export const EQUIPMENT_STATUS_TONE: Record<EquipmentStatus, string> = {
  run: "bg-emerald-100 text-emerald-900",
  idle: "bg-amber-100 text-amber-900",
  to: "bg-blue-100 text-blue-900",
  repair: "bg-red-100 text-red-900",
};

export const REPAIR_KIND_LABELS: Record<RepairKind, string> = {
  fail: "Авария",
  repair: "Плановый ремонт",
  maintenance: "ТО",
};

export const REPAIR_KIND_TONE: Record<RepairKind, string> = {
  fail: "bg-red-100 text-red-900",
  repair: "bg-amber-100 text-amber-900",
  maintenance: "bg-blue-100 text-blue-900",
};

export const REPAIR_STATUS_LABELS: Record<RepairStatus, string> = {
  open: "Зарегистрирована",
  work: "В ремонте",
  done: "Устранено",
};

export const REPAIR_STATUS_TONE: Record<RepairStatus, string> = {
  open: "bg-red-100 text-red-900",
  work: "bg-amber-100 text-amber-900",
  done: "bg-emerald-100 text-emerald-900",
};

export const MAINTENANCE_TONE: Record<MaintenanceState, string> = {
  overdue: "bg-red-100 text-red-900",
  soon: "bg-amber-100 text-amber-900",
  ok: "bg-emerald-100 text-emerald-900",
};

/** Доля «0.6010» → «60%». */
export function pct(value: string): string {
  return `${Math.round(Number(value) * 100)}%`;
}

export function utilClass(value: string): string {
  const v = Number(value);
  return v >= 0.7 ? "text-emerald-600" : v >= 0.5 ? "text-amber-600" : "text-red-600";
}

export function utilBg(value: string, days: number): string {
  if (!days) return "#f4f5f7";
  const v = Number(value);
  return v >= 0.7 ? "#cfe3d6" : v >= 0.5 ? "#f7e7b8" : "#f3c0c0";
}

/** «2026-10-26» → «26.10». */
export function shortDate(day: string): string {
  return `${day.slice(8, 10)}.${day.slice(5, 7)}`;
}

export function num(value: string | number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** ISO с зоной → значение `datetime-local` в локальном времени браузера. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Значение `datetime-local` → ISO для API (зона браузера). */
export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  return new Date(value).toISOString();
}

export function nowLocalInput(): string {
  return toLocalInput(new Date().toISOString());
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatLocal(iso: string | null | undefined): string {
  if (!iso) return "—";
  const v = toLocalInput(iso);
  return `${v.slice(8, 10)}.${v.slice(5, 7)} ${v.slice(11, 16)}`;
}
