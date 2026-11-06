"use client";

/**
 * Заглушка вкладок «Материалы» и «Оснастка и расходники» карточки заказа. Настоящий
 * компонент с теми же экспортом и пропсами пишется в модуле снабжения и заменит этот
 * файл при слиянии веток.
 */
export function OrderSupplyTab({ orderId, kind }: { orderId: string; kind: "mat" | "tool" }) {
  return (
    <div
      className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground"
      data-order-id={orderId}
      data-kind={kind}
      data-testid="order-supply-stub"
    >
      Раздел появится после подключения модуля
    </div>
  );
}
