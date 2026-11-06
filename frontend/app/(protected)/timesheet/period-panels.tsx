"use client";

import { Download } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import type { CheckOut, MonthGridOut, PeriodReviewOut } from "@/lib/api/endpoints";
import { formatDateTime } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import { PERIOD_EVENT_LABELS, hours, monthTitle, objectLabel } from "./labels";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function ChecksPanel({
  checks,
  blocking,
  review,
}: {
  checks: CheckOut[];
  blocking: number;
  review: PeriodReviewOut | undefined;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Panel title={`Проверки перед подачей${blocking ? ` · блокирующих: ${blocking}` : ""}`}>
        <div className="flex flex-col gap-1.5" data-testid="timesheet-checks">
          {checks.length === 0 && (
            <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900">Все проверки пройдены</div>
          )}
          {checks.map((c, i) => (
            <div
              key={i}
              className={cn(
                "rounded-lg px-3 py-2 text-sm",
                c.is_blocking ? "bg-red-50 text-red-900" : "bg-amber-50 text-amber-900",
              )}
            >
              {c.is_blocking ? "⛔ " : "⚠ "}
              {c.text}
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Подтверждение руководителей проектов">
        {!review || review.managers.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {review?.period.status === "on_review" ? "Часов на заказы нет." : "Визы собираются после подачи табеля."}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {review.managers.map((m) => (
              <div key={m.manager_id} className="rounded-lg border px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <b>{m.manager_name || "Менеджер"}</b>
                  <span className="flex-1" />
                  {m.confirmed ? (
                    <span className="text-xs text-emerald-700">подтвердил</span>
                  ) : review.period.status === "on_review" ? (
                    <span className="text-xs text-amber-700">ждём подтверждения</span>
                  ) : (
                    <span className="text-xs text-muted-foreground">после подачи</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {m.orders.map((o) => `${o.order_label || "заказ"}: ${hours(o.hours)} ч`).join(" · ")}
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Линейный руководитель отвечает за то, что часы отработаны, руководитель проекта — за то, что они обоснованно
          легли на его заказ.
        </p>
      </Panel>
    </div>
  );
}

export function SummaryPanel({
  grid,
  review,
  departmentId,
  month,
}: {
  grid: MonthGridOut;
  review: PeriodReviewOut | undefined;
  departmentId: string;
  month: string;
}) {
  const base = `/api/v1/timesheet/departments/${departmentId}/periods/${month}/packages`;
  return (
    <Panel title={`Свод периода · ${monthTitle(month)}`}>
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="py-1 text-left font-medium">Вид времени</th>
            <th className="text-left font-medium">Код 1С</th>
            <th className="text-right font-medium">Часы</th>
          </tr>
        </thead>
        <tbody>
          {grid.by_code.map((c) => (
            <tr key={c.code} className="border-t">
              <td className="py-1">{c.name}</td>
              <td>{c.code}</td>
              <td className="text-right tabular-nums">{hours(c.hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="mt-4 mb-1 text-sm font-semibold">База распределения затрат</h3>
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="py-1 text-left font-medium">Объект</th>
            <th className="text-left font-medium">Аналитика 1С</th>
            <th className="text-right font-medium">Часы</th>
          </tr>
        </thead>
        <tbody>
          {grid.by_object.map((o) => (
            <tr key={`${o.target}-${o.order_id ?? ""}`} className="border-t">
              <td className="py-1">{objectLabel(o.target, o.order_label)}</td>
              <td className="text-muted-foreground">{o.analytics}</td>
              <td className="text-right tabular-nums">{hours(o.hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="mt-4 mb-1 text-sm font-semibold">Обмен с 1С</h3>
      <p className="mb-2 text-xs text-muted-foreground">
        Табель по видам времени и база распределения затрат — файлы JSON. Передаются часы и доли, суммы начисляет 1С:ЗУП.
      </p>
      <div className="flex flex-wrap gap-2">
        <a className={buttonVariants({ variant: "outline", size: "sm" })} href={`${base}/timesheet`} download>
          <Download aria-hidden />
          Табель (JSON)
        </a>
        <a className={buttonVariants({ variant: "outline", size: "sm" })} href={`${base}/cost_allocation`} download>
          <Download aria-hidden />
          База распределения (JSON)
        </a>
      </div>

      <h3 className="mt-4 mb-1 text-sm font-semibold">Журнал периода</h3>
      {!review || review.events.length === 0 ? (
        <p className="text-sm text-muted-foreground">Переходов ещё не было.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm" data-testid="period-journal">
          {review.events.map((e, i) => (
            <li key={i} className="flex gap-2">
              <time className="shrink-0 text-xs text-muted-foreground tabular-nums">{formatDateTime(e.created_at)}</time>
              <span>
                <b>{e.actor_name || "—"}</b>: {PERIOD_EVENT_LABELS[e.kind]}
                {e.manager_name ? ` (${e.manager_name})` : ""}
                {e.version > 1 ? ` · версия ${e.version}` : ""}
                {e.comment ? ` — ${e.comment}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
