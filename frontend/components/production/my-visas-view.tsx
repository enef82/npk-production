"use client";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useGetProductionBoard, useGetSalesBoard, useListMyProductionVisas, useListMySalesVisas } from "@/lib/api/endpoints";
import { fd } from "@/lib/production/dates";
import { stageTitle } from "@/lib/production/stages";

import { HealthDot, Note, Pill, TABLE } from "./bits";
import { useCards } from "./card-host";

/**
 * «Мои визы» (`myVisaList`/`visaListDialog` прототипа): этапы заявок и заказов, где я
 * ответственный и визы нет, и операции на визе. Виза этапа ставится здесь же диалогом,
 * операция открывается карточкой — там виза требует проверки контроля и предшественников.
 */
export function MyVisasView() {
  const cards = useCards();
  const orderVisas = useListMyProductionVisas();
  const inquiryVisas = useListMySalesVisas();
  // Карточки доски нужны диалогу визы этапа (способности, текущий этап, ответственный).
  const orders = useGetProductionBoard();
  const inquiries = useGetSalesBoard();
  const loading = orderVisas.isLoading || inquiryVisas.isLoading;
  const total = (orderVisas.data?.length ?? 0) + (inquiryVisas.data?.length ?? 0);

  return (
    <div className="flex flex-col gap-3 p-4">
      <h1 className="text-lg font-semibold">Мои визы</h1>
      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : !total ? (
        <Note tone="ok">Все визы поставлены.</Note>
      ) : (
        <table className={TABLE} data-testid="my-visas-table">
          <thead>
            <tr>
              <th>Заявка / заказ</th>
              <th>Что визировать</th>
              <th>Этап</th>
              <th>Срок</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(inquiryVisas.data ?? []).map((v) => {
              const card = inquiries.data?.find((c) => c.id === v.inquiry_id);
              return (
                <tr key={`i${v.inquiry_id}`}>
                  <td>
                    <b>{v.number}</b>
                    <div className="text-xs text-muted-foreground">
                      {v.product_name} × {Number(v.quantity)} · {v.customer_name}
                    </div>
                  </td>
                  <td>{v.text}</td>
                  <td>
                    <Pill>{stageTitle(v.stage)}</Pill>
                  </td>
                  <td>{fd(v.due_date)}</td>
                  <td className="whitespace-nowrap">
                    <Button
                      size="xs"
                      className="bg-emerald-700 hover:bg-emerald-700/90"
                      disabled={!card}
                      onClick={() => card && cards.approveStage({ kind: "inquiry", card })}
                    >
                      Завизировать
                    </Button>{" "}
                    <Button size="xs" variant="outline" onClick={() => cards.openInquiry(v.inquiry_id)}>
                      Карточка
                    </Button>
                  </td>
                </tr>
              );
            })}
            {(orderVisas.data ?? []).map((v) => {
              const card = orders.data?.find((c) => c.id === v.order_id);
              return (
                <tr key={`o${v.order_id}${v.operation_id ?? ""}`}>
                  <td>
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                      <HealthDot color={v.health.color} title={v.health.text} />
                      <b>{v.order_number}</b>
                    </span>
                    <div className="text-xs text-muted-foreground">
                      {v.product_name} × {Number(v.quantity)} · {v.customer_name}
                    </div>
                  </td>
                  <td>{v.text}</td>
                  <td>
                    <Pill>{stageTitle(v.stage)}</Pill>
                  </td>
                  <td>{fd(v.due_date)}</td>
                  <td className="whitespace-nowrap">
                    {v.kind === "stage" ? (
                      <Button
                        size="xs"
                        className="bg-emerald-700 hover:bg-emerald-700/90"
                        disabled={!card}
                        onClick={() => card && cards.approveStage({ kind: "order", card })}
                      >
                        Завизировать
                      </Button>
                    ) : (
                      <Button size="xs" className="bg-emerald-700 hover:bg-emerald-700/90" onClick={() => cards.openOperation(v.operation_id!)}>
                        Открыть операцию
                      </Button>
                    )}{" "}
                    <Button size="xs" variant="outline" onClick={() => cards.openOrder(v.order_id, v.kind === "operation" ? "state" : "main")}>
                      Карточка
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
