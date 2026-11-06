import { Badge } from "@/components/ui/badge";
import type { LineCategory, LineKind, LineStatus } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

export const LINE_STATUS_LABELS: Record<LineStatus, string> = {
  draft: "Черновик",
  sent: "Передано в закупку",
  ordered: "Заказано",
  received: "Принято на склад",
  reserved: "Резерв со склада",
  issued: "Передано в производство",
};

export const LINE_CATEGORY_LABELS: Record<LineCategory, string> = {
  material: "Материал",
  tool: "Инструмент",
  fixture: "Оснастка",
  consumable: "Расходники",
};

export const LINE_KIND_LABELS: Record<LineKind, string> = {
  mat: "Материалы и комплектующие",
  tool: "Оснастка, инструмент, расходники",
};

const STATUS_TONE: Record<LineStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  sent: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  ordered: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  received: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  reserved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  issued: "bg-emerald-200 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
};

export function LineStatusBadge({ status }: { status: LineStatus }) {
  return (
    <Badge variant="secondary" className={cn("whitespace-nowrap", STATUS_TONE[status])}>
      {LINE_STATUS_LABELS[status]}
    </Badge>
  );
}

export function LateBadge({ days }: { days: number }) {
  if (days <= 0) return null;
  return (
    <Badge variant="destructive" className="whitespace-nowrap">
      +{days} дн.
    </Badge>
  );
}

const rub = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

export function formatRub(value: string | number): string {
  const num = typeof value === "string" ? Number(value) : value;
  return Number.isNaN(num) ? "—" : `${rub.format(num)} ₽`;
}

export function formatQty(value: string | number | null): string {
  if (value === null) return "—";
  const num = typeof value === "string" ? Number(value) : value;
  return Number.isNaN(num) ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(num);
}

export function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function addDaysIso(days: number): string {
  const now = new Date();
  now.setDate(now.getDate() + days);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}
