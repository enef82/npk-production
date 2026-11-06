import { cn } from "@/lib/utils";

/** Плитка показателя: крупное значение и подпись под ним (как `.kpi` прототипа). */
export function Kpi({
  value,
  label,
  tone,
  title,
}: {
  value: React.ReactNode;
  label: string;
  tone?: "bad" | "warn" | "ok";
  title?: string;
}) {
  return (
    <div className="min-w-36 flex-1 rounded-xl border bg-card px-4 py-3" title={title}>
      <div
        className={cn(
          "text-xl font-semibold tabular-nums",
          tone === "bad" && "text-red-600",
          tone === "warn" && "text-amber-600",
          tone === "ok" && "text-emerald-600",
        )}
      >
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function KpiRow({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-3">{children}</div>;
}
