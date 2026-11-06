import type { InquiryStage, JournalKind, OperationStatus, OrderStage } from "@/lib/api/endpoints";

/**
 * Восемь колонок доски (§6): три этапа заявки из `sales` и пять этапов заказа из
 * `production`. Порядок — порядок прохождения; переход возможен только на соседний.
 */
export type BoardStage = Exclude<InquiryStage, "launched" | "lost"> | OrderStage;

export const BOARD_STAGES: { id: BoardStage; title: string; hint: string; kind: "inquiry" | "order" }[] = [
  { id: "new", title: "Новые заявки", hint: "Заявка", kind: "inquiry" },
  { id: "calc", title: "Просчёт", hint: "Заявка", kind: "inquiry" },
  { id: "approval", title: "Согласование КП", hint: "Заявка", kind: "inquiry" },
  { id: "launch", title: "Запуск в работу", hint: "Заказ", kind: "order" },
  { id: "prep", title: "Подготовка производства", hint: "Заказ", kind: "order" },
  { id: "prod", title: "Изготовление", hint: "Заказ", kind: "order" },
  { id: "qc", title: "ОТК и испытания", hint: "Заказ", kind: "order" },
  { id: "done", title: "Отгружено", hint: "Заказ", kind: "order" },
];

export const STAGE_INDEX: Record<BoardStage, number> = Object.fromEntries(
  BOARD_STAGES.map((s, i) => [s.id, i]),
) as Record<BoardStage, number>;

export function stageTitle(stage: string): string {
  return BOARD_STAGES.find((s) => s.id === stage)?.title ?? (stage === "lost" ? "Проиграна" : stage === "launched" ? "Запущена" : stage);
}

export function isOrderStage(stage: string): stage is OrderStage {
  return BOARD_STAGES.some((s) => s.id === stage && s.kind === "order");
}

/**
 * Клиентская проверка перехода — только то, что видно без сервера (`checkMove`
 * прототипа: порядок и направление). Правила содержимого (калькуляция, КД, визы
 * операций) проверяет сервер, его ошибка показывается тостом.
 */
export function checkMove(from: BoardStage, to: BoardStage): string | null {
  if (from === to) return null;
  if (isOrderStage(from) && !isOrderStage(to)) return "Заказ уже запущен — вернуть его в заявки нельзя.";
  const a = STAGE_INDEX[from];
  const b = STAGE_INDEX[to];
  if (b < a) return a - b > 1 ? "Вернуть можно только на один этап назад." : null;
  if (b - a > 1) return `Этапы проходятся по порядку — нельзя перескочить через «${BOARD_STAGES[a + 1].title}».`;
  return null;
}

export const OPERATION_STATUS_LABELS: Record<OperationStatus, string> = {
  wait: "Ожидает",
  work: "В работе",
  check: "На визе",
  done: "Выполнено",
};

export const PHASE_LABELS: Record<string, string> = {
  prep: "Подготовка производства",
  prod: "Изготовление",
  qc: "ОТК и испытания",
};

export const JOURNAL_KIND_LABELS: Record<JournalKind, string> = {
  stage: "Этап",
  visa: "Виза",
  status: "Статус",
  plan: "План",
  comment: "Комментарий",
  qc: "Контроль",
  proc: "Закупка",
  doc: "Документ",
};
