"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useGetInquiry, type InquiryOut } from "@/lib/api/endpoints";
import { fdl } from "@/lib/production/dates";
import { BOARD_STAGES, STAGE_INDEX, stageTitle, type BoardStage } from "@/lib/production/stages";
import { cn } from "@/lib/utils";

import { Pill, Visa } from "./bits";
import { useCards, type InquiryTab } from "./card-host";
import { CalcTables, InquiryMainTab, InquiryPlanTab } from "./inquiry-tabs";

const TABS: { id: InquiryTab; label: string }[] = [
  { id: "main", label: "Основное" },
  { id: "calc", label: "Калькуляция" },
  { id: "plan", label: "План" },
];

/** Карточка заявки: до запуска у неё нет хода, документов и журнала — это вкладки заказа. */
export function InquirySheet({
  inquiryId,
  tab,
  onTabChange,
  onClose,
}: {
  inquiryId: string | null;
  tab: InquiryTab;
  onTabChange: (tab: InquiryTab) => void;
  onClose: () => void;
}) {
  const query = useGetInquiry(inquiryId ?? "", { query: { enabled: !!inquiryId } });
  const inquiry = query.data && query.data.id === inquiryId ? query.data : undefined;

  return (
    <Sheet open={!!inquiryId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-[min(1100px,97vw)] gap-0 p-0 data-[side=right]:sm:max-w-[min(1100px,97vw)]"
        data-testid="inquiry-sheet"
      >
        {!inquiry ? (
          <div className="flex flex-col gap-3 p-6">
            <SheetTitle className="sr-only">Карточка заявки</SheetTitle>
            <Skeleton className="h-7 w-64" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
            <InquiryHeader inquiry={inquiry} onClose={onClose} />
            <div className="flex flex-wrap gap-5 border-b px-5">
              {TABS.map((t) => (
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
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-auto px-5 pt-4 pb-8" data-testid={`inquiry-tab-${tab}`}>
              {tab === "main" && <InquiryMainTab inquiry={inquiry} onGoCalc={() => onTabChange("calc")} />}
              {tab === "calc" && <CalcTables inquiry={inquiry} />}
              {tab === "plan" && <InquiryPlanTab inquiry={inquiry} />}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function InquiryHeader({ inquiry, onClose }: { inquiry: InquiryOut; onClose: () => void }) {
  const cards = useCards();
  const open = inquiry.stage === "new" || inquiry.stage === "calc" || inquiry.stage === "approval";
  const index = open ? STAGE_INDEX[inquiry.stage as BoardStage] : -1;
  const next = open ? BOARD_STAGES[index + 1] : undefined;
  const current = inquiry.approvals.find((a) => a.stage === inquiry.stage);
  const target = { kind: "inquiry" as const, card: inquiry };
  const showNext = next && (next.id === "launch" ? inquiry.abilities.can_launch : inquiry.abilities.can_move);

  return (
    <div className="border-b px-5 pt-4">
      <div className="flex flex-wrap items-center gap-2.5">
        <SheetTitle className="text-lg font-semibold">{inquiry.number}</SheetTitle>
        <Pill tone={inquiry.health.color}>{inquiry.health.text}</Pill>
        {inquiry.order_id ? (
          <button type="button" onClick={() => cards.openOrder(inquiry.order_id!)}>
            <Pill tone="b">заказ создан →</Pill>
          </button>
        ) : null}
        <span className="flex-1" />
        {inquiry.abilities.can_lose && open ? (
          <Button size="sm" variant="outline" onClick={() => cards.lose(inquiry)}>
            Проигрыш
          </Button>
        ) : null}
        {showNext ? (
          <Button size="sm" onClick={() => cards.moveTo(target, next!.id)}>
            → {next!.title}
          </Button>
        ) : null}
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Закрыть">
          <X />
        </Button>
      </div>
      <SheetDescription className="mt-1 mb-2">
        {inquiry.product_name || "изделие не указано"} × {Number(inquiry.quantity)} · {inquiry.customer_name} · {inquiry.object_name}
      </SheetDescription>
      <div className="mb-2 flex flex-wrap gap-1">
        {BOARD_STAGES.map((s, i) => (
          <span
            key={s.id}
            className={cn(
              "rounded px-2 py-0.5 text-[11px]",
              i < index || (!open && inquiry.stage === "launched" && i <= 3)
                ? "bg-emerald-50 text-emerald-700"
                : i === index
                  ? "bg-blue-600 text-white"
                  : "bg-muted text-muted-foreground",
            )}
          >
            {s.title}
          </span>
        ))}
      </div>
      <div className="mb-2.5 flex flex-wrap items-center gap-2.5 rounded-lg bg-muted px-2.5 py-1.5 text-[13px]">
        <b>{stageTitle(inquiry.stage)}</b>
        <span className="text-xs text-muted-foreground">ответственный</span>
        <span>{inquiry.stage_responsible_name || "—"}</span>
        {!open ? null : inquiry.stage === "new" ? (
          <span className="text-xs text-muted-foreground">виза не требуется</span>
        ) : current?.approved_at ? (
          <Visa>
            виза {current.approved_by_name} · {fdl(current.approved_at.slice(0, 10))}
          </Visa>
        ) : inquiry.abilities.can_approve_stage ? (
          <Button size="xs" className="bg-emerald-700 hover:bg-emerald-700/90" onClick={() => cards.approveStage(target)}>
            Завизировать этап
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">ждёт визы</span>
        )}
      </div>
    </div>
  );
}
