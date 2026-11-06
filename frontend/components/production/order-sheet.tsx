"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { OrderSupplyTab } from "@/components/supply/order-supply-tab";
import {
  useGetProductionOrder,
  useListProductionJournal,
  useListProductionOrderDocuments,
  type OrderOut,
} from "@/lib/api/endpoints";
import { fdl } from "@/lib/production/dates";
import { BOARD_STAGES, STAGE_INDEX, stageTitle, type BoardStage } from "@/lib/production/stages";
import { cn } from "@/lib/utils";

import { Pill, Visa } from "./bits";
import { useCards, type OrderTab } from "./card-host";
import { OrderCalcTab, OrderDocsTab, OrderJournalTab, OrderMainTab, OrderPlanTab, OrderStateTab } from "./order-tabs";
import { CommentButton } from "./comment-button";

const TABS: { id: OrderTab; label: string }[] = [
  { id: "main", label: "Основное" },
  { id: "calc", label: "Калькуляция" },
  { id: "plan", label: "План" },
  { id: "state", label: "Состояние" },
  { id: "docs", label: "Документы" },
  { id: "mat", label: "Материалы" },
  { id: "tool", label: "Оснастка" },
  { id: "journal", label: "Журнал" },
];

/** Карточка производственного заказа — боковая панель (`renderDrawer` прототипа). */
export function OrderSheet({
  orderId,
  tab,
  onTabChange,
  onClose,
}: {
  orderId: string | null;
  tab: OrderTab;
  onTabChange: (tab: OrderTab) => void;
  onClose: () => void;
}) {
  const query = useGetProductionOrder(orderId ?? "", { query: { enabled: !!orderId } });
  const docs = useListProductionOrderDocuments(orderId ?? "", { query: { enabled: !!orderId } });
  const journal = useListProductionJournal(orderId ?? "", undefined, { query: { enabled: !!orderId } });
  const order = query.data && query.data.id === orderId ? query.data : undefined;

  return (
    <Sheet open={!!orderId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-[min(1100px,97vw)] gap-0 p-0 data-[side=right]:sm:max-w-[min(1100px,97vw)]"
        data-testid="order-sheet"
      >
        {!order ? (
          <div className="flex flex-col gap-3 p-6">
            <SheetTitle className="sr-only">Карточка заказа</SheetTitle>
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
            <OrderHeader order={order} onClose={onClose} />
            <div className="flex flex-wrap gap-5 border-b px-5">
              {TABS.map((t) => {
                const count =
                  t.id === "docs" ? docs.data?.length : t.id === "journal" ? journal.data?.length : undefined;
                return (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={tab === t.id}
                    onClick={() => onTabChange(t.id)}
                    className={cn(
                      "-mb-px border-b-2 border-transparent py-2 text-sm text-muted-foreground",
                      tab === t.id && "border-blue-600 font-medium text-foreground",
                    )}
                  >
                    {t.label}
                    {count ? <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px]">{count}</span> : null}
                  </button>
                );
              })}
            </div>
            <div className="flex-1 overflow-auto px-5 pt-4 pb-8" data-testid={`order-tab-${tab}`}>
              {tab === "main" && <OrderMainTab order={order} />}
              {tab === "calc" && <OrderCalcTab order={order} />}
              {tab === "plan" && <OrderPlanTab order={order} />}
              {tab === "state" && <OrderStateTab order={order} />}
              {tab === "docs" && <OrderDocsTab order={order} />}
              {tab === "mat" && <OrderSupplyTab orderId={order.id} kind="mat" />}
              {tab === "tool" && <OrderSupplyTab orderId={order.id} kind="tool" />}
              {tab === "journal" && <OrderJournalTab order={order} />}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function OrderHeader({ order, onClose }: { order: OrderOut; onClose: () => void }) {
  const cards = useCards();
  const index = STAGE_INDEX[order.stage as BoardStage];
  const next = BOARD_STAGES[index + 1];
  const current = order.approvals.find((a) => a.stage === order.stage);
  const target = { kind: "order" as const, card: order };

  return (
    <div className="border-b px-5 pt-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <SheetTitle className="text-lg font-semibold">{order.number}</SheetTitle>
        {order.inquiry_number ? <Pill>заявка {order.inquiry_number}</Pill> : null}
        <Pill tone={order.health.color}>{order.health.text}</Pill>
        <span className="flex-1" />
        {next && order.abilities.can_move ? (
          <Button size="sm" onClick={() => cards.moveTo(target, next.id)}>
            → {next.title}
          </Button>
        ) : null}
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Закрыть">
          <X />
        </Button>
      </div>
      <SheetDescription className="mt-1 mb-2">
        {order.product_name} × {Number(order.quantity)} · {order.customer_name} · {order.object_name}
      </SheetDescription>
      <div className="mb-2 flex flex-wrap gap-1">
        {BOARD_STAGES.map((s, i) => {
          const approval = order.approvals.find((a) => a.stage === s.id);
          return (
            <span
              key={s.id}
              title={approval ? `${approval.responsible_name}${approval.approved_at ? " · виза " + fdl(approval.approved_at.slice(0, 10)) : ""}` : ""}
              className={cn(
                "rounded px-2 py-0.5 text-[11px]",
                i < index ? "bg-emerald-50 text-emerald-700" : i === index ? "bg-blue-600 text-white" : "bg-muted text-muted-foreground",
              )}
            >
              {s.title}
            </span>
          );
        })}
      </div>
      <div className="mb-2.5 flex flex-wrap items-center gap-2.5 rounded-lg bg-muted px-2.5 py-1.5 text-[13px]">
        <b>{stageTitle(order.stage)}</b>
        <span className="text-xs text-muted-foreground">ответственный</span>
        <span>{order.stage_responsible_name || "—"}</span>
        {order.stage === "done" ? null : current?.approved_at ? (
          <Visa>
            виза {current.approved_by_name} · {fdl(current.approved_at.slice(0, 10))}
          </Visa>
        ) : order.abilities.can_approve_stage ? (
          <Button size="xs" className="bg-emerald-700 hover:bg-emerald-700/90" onClick={() => cards.approveStage(target)}>
            Завизировать этап
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">ждёт визы</span>
        )}
        {order.order_abilities.can_comment ? <CommentButton orderId={order.id} /> : null}
      </div>
    </div>
  );
}
