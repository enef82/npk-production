"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  approveInquiryStage,
  approveProductionOrderStage,
  moveInquiryStage,
  moveProductionOrderStage,
  type InquiryCardOut,
  type InquiryStage,
  type OrderCardOut,
  type OrderStage,
} from "@/lib/api/endpoints";
import { checkMove, STAGE_INDEX, stageTitle, type BoardStage } from "@/lib/production/stages";
import { useAction } from "@/lib/production/use-action";

import { InquirySheet } from "./inquiry-sheet";
import { OperationDialog } from "./operation-dialog";
import { OrderSheet } from "./order-sheet";
import { InfoDialog, LaunchDialog, LoseDialog, TextDialog } from "./stage-dialogs";

export type StageTarget = { kind: "order"; card: OrderCardOut } | { kind: "inquiry"; card: InquiryCardOut };

export type OrderTab = "main" | "calc" | "plan" | "state" | "docs" | "mat" | "tool" | "journal";
export type InquiryTab = "main" | "calc" | "plan";

type CardsApi = {
  openOrder: (id: string, tab?: OrderTab) => void;
  openInquiry: (id: string, tab?: InquiryTab) => void;
  openOperation: (id: string) => void;
  /** Переход этапа с нужным диалогом: виза, причина возврата, запуск. */
  moveTo: (target: StageTarget, to: BoardStage) => void;
  /** Виза текущего этапа без перехода. */
  approveStage: (target: StageTarget) => void;
  lose: (inquiry: InquiryCardOut) => void;
};

const CardsContext = createContext<CardsApi | null>(null);

export function useCards(): CardsApi {
  const ctx = useContext(CardsContext);
  if (!ctx) throw new Error("useCards должен вызываться внутри CardHost.");
  return ctx;
}

type Pending =
  | { type: "visa"; target: StageTarget; then?: BoardStage }
  | { type: "back"; target: StageTarget; to: BoardStage }
  | { type: "need-visa"; target: StageTarget }
  | { type: "launch"; inquiry: InquiryCardOut }
  | { type: "lose"; inquiry: InquiryCardOut }
  | null;

/**
 * Хозяин карточек: боковая панель заказа/заявки, окно операции и диалоги переходов
 * этапов — одни на экран, вызываются с доски, Ганта, «Моих виз» и из самих карточек.
 * `basePath` — адрес экрана: открытая карточка отражается в адресной строке
 * (`/orders/{id}`, `/inquiries/{id}`), закрытая возвращает адрес экрана.
 */
export function CardHost({
  basePath,
  initial,
  children,
}: {
  basePath?: string;
  initial?: { kind: "order" | "inquiry"; id: string };
  children: React.ReactNode;
}) {
  const { run } = useAction();
  const [order, setOrder] = useState<{ id: string; tab: OrderTab } | null>(
    initial?.kind === "order" ? { id: initial.id, tab: "main" } : null,
  );
  const [inquiry, setInquiry] = useState<{ id: string; tab: InquiryTab } | null>(
    initial?.kind === "inquiry" ? { id: initial.id, tab: "main" } : null,
  );
  const [operationId, setOperationId] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);

  const syncUrl = useCallback(
    (path: string | null) => {
      if (!basePath || typeof window === "undefined") return;
      const next = path ?? basePath;
      if (window.location.pathname !== next) window.history.replaceState(null, "", next);
    },
    [basePath],
  );

  const openOrder = useCallback(
    (id: string, tab: OrderTab = "main") => {
      setInquiry(null);
      setOrder({ id, tab });
      syncUrl(`/orders/${id}`);
    },
    [syncUrl],
  );
  const openInquiry = useCallback(
    (id: string, tab: InquiryTab = "main") => {
      setOrder(null);
      setInquiry({ id, tab });
      syncUrl(`/inquiries/${id}`);
    },
    [syncUrl],
  );

  const doMove = useCallback(
    async (target: StageTarget, to: BoardStage, comment = "") => {
      const label = target.card.number;
      return run<unknown>(
        () =>
          target.kind === "order"
            ? moveProductionOrderStage(target.card.id, { to: to as OrderStage, comment })
            : moveInquiryStage(target.card.id, { to: to as InquiryStage, comment }),
        `${label}: ${stageTitle(to)}`,
      );
    },
    [run],
  );

  const moveTo = useCallback(
    (target: StageTarget, to: BoardStage) => {
      const from = target.card.stage as BoardStage;
      if (from === to) return;
      const error = checkMove(from, to);
      if (error) {
        toast.error(error);
        return;
      }
      const back = STAGE_INDEX[to] < STAGE_INDEX[from];
      if (target.kind === "inquiry" && to === "launch") {
        if (!target.card.abilities.can_launch) {
          toast.error("Запускает в работу начальник производства.");
          return;
        }
        setPending({ type: "launch", inquiry: target.card });
        return;
      }
      if (!target.card.abilities.can_move) {
        toast.error("Этап переводит ответственный за этап, менеджер или начальник производства.");
        return;
      }
      if (back) {
        setPending({ type: "back", target, to });
        return;
      }
      if (from !== "new" && !target.card.stage_approved) {
        setPending(
          target.card.abilities.can_approve_stage ? { type: "visa", target, then: to } : { type: "need-visa", target },
        );
        return;
      }
      void doMove(target, to);
    },
    [doMove],
  );

  const approveStage = useCallback((target: StageTarget) => setPending({ type: "visa", target }), []);
  const lose = useCallback((inq: InquiryCardOut) => setPending({ type: "lose", inquiry: inq }), []);

  const api = useMemo<CardsApi>(
    () => ({ openOrder, openInquiry, openOperation: setOperationId, moveTo, approveStage, lose }),
    [openOrder, openInquiry, moveTo, approveStage, lose],
  );

  const close = () => setPending(null);
  const visaTarget = pending?.type === "visa" ? pending.target : null;

  return (
    <CardsContext.Provider value={api}>
      {children}

      <OrderSheet
        orderId={order?.id ?? null}
        tab={order?.tab ?? "main"}
        onTabChange={(tab) => setOrder((o) => (o ? { ...o, tab } : o))}
        onClose={() => {
          setOrder(null);
          syncUrl(null);
        }}
      />
      <InquirySheet
        inquiryId={inquiry?.id ?? null}
        tab={inquiry?.tab ?? "main"}
        onTabChange={(tab) => setInquiry((i) => (i ? { ...i, tab } : i))}
        onClose={() => {
          setInquiry(null);
          syncUrl(null);
        }}
      />
      <OperationDialog operationId={operationId} onOpenChange={(open) => !open && setOperationId(null)} />

      <TextDialog
        open={pending?.type === "visa"}
        title={visaTarget ? `Виза: этап «${stageTitle(visaTarget.card.stage)}»` : ""}
        description={
          visaTarget ? `${visaTarget.card.number} · ${visaTarget.card.product_name} · ${visaTarget.card.customer_name}` : ""
        }
        label="Комментарий к визе (необязательно)"
        placeholder="Например: калькуляция проверена, наценка согласована"
        okText={pending?.type === "visa" && pending.then ? "Завизировать и перевести" : "Завизировать"}
        onOpenChange={(open) => !open && close()}
        onSubmit={async (comment) => {
          if (pending?.type !== "visa") return;
          const { target, then } = pending;
          const ok = await run<unknown>(
            () =>
              target.kind === "order"
                ? approveProductionOrderStage(target.card.id, target.card.stage, { comment })
                : approveInquiryStage(target.card.id, target.card.stage as InquiryStage, { comment }),
            then ? undefined : "Виза поставлена",
          );
          if (ok && then) await doMove(target, then);
        }}
      />
      <TextDialog
        open={pending?.type === "back"}
        title={pending?.type === "back" ? `Вернуть на этап «${stageTitle(pending.to)}»?` : ""}
        label="Причина возврата (в журнал)"
        required
        okText="Вернуть"
        onOpenChange={(open) => !open && close()}
        onSubmit={async (comment) => {
          if (pending?.type === "back") await doMove(pending.target, pending.to, comment);
        }}
      />
      <InfoDialog
        open={pending?.type === "need-visa"}
        title={pending?.type === "need-visa" ? `Этап «${stageTitle(pending.target.card.stage)}» не завизирован` : ""}
        onOpenChange={(open) => !open && close()}
      >
        {pending?.type === "need-visa" ? (
          <p>
            Перевести дальше можно после визы ответственного за этап:{" "}
            <b>{pending.target.card.stage_responsible_name || "не назначен"}</b>. Ответственного можно сменить в
            карточке.
          </p>
        ) : null}
      </InfoDialog>
      <LaunchDialog
        inquiry={pending?.type === "launch" ? pending.inquiry : null}
        open={pending?.type === "launch"}
        onOpenChange={(open) => !open && close()}
        onLaunched={(orderId) => openOrder(orderId, "plan")}
      />
      <LoseDialog
        inquiry={pending?.type === "lose" ? pending.inquiry : null}
        open={pending?.type === "lose"}
        onOpenChange={(open) => {
          if (!open) {
            close();
          }
        }}
      />
    </CardsContext.Provider>
  );
}
