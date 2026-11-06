"use client";

/**
 * Заглушка блока контроля качества в карточке операции. Настоящий компонент с теми же
 * экспортом и пропсами пишется в модуле качества и заменит этот файл при слиянии веток.
 */
export function OperationQcPanel({
  operationId,
  workCenterId,
  canRecord,
}: {
  operationId: string;
  workCenterId: string;
  canRecord?: boolean;
}) {
  return (
    <div
      className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground"
      data-operation-id={operationId}
      data-work-center-id={workCenterId}
      data-can-record={canRecord ? "1" : "0"}
      data-testid="operation-qc-stub"
    >
      Раздел появится после подключения модуля
    </div>
  );
}
