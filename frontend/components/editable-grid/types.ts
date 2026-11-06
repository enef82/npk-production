/**
 * Контракт `EditableGrid`. Компонент знает только про данные, колонки и обработчики —
 * ни слова про заявки, расчёты или блоки КП. Любое доменное знание (что «стоимость»
 * это «количество x цена», какие статусы допустимы, откуда берётся ставка) живёт у
 * потребителя: в `setValue` колонки и в `validateRow`.
 */

/**
 * - `text`     — произвольная строка;
 * - `decimal`  — число, хранится каноничной строкой без потери точности, НЕ округляется;
 * - `money`    — число, при коммите квантуется до копейки (`roundMoney`, `HALF_UP`);
 * - `readonly` — только показ, потребитель заполняет поле сам через `setValue` других колонок.
 */
export type EditableGridColumnKind = "text" | "decimal" | "money" | "readonly";

export type EditableGridColumn<TRow> = {
  id: string;
  header: string;
  kind: EditableGridColumnKind;
  /** Значение ячейки как каноничная строка (для чисел — из `normalizeDecimal`). */
  accessor: (row: TRow) => string;
  /**
   * Новая строка после правки ячейки. Здесь потребитель пересчитывает производные
   * поля этой же строки (например `amount = quantity x price`). Обязателен для всех
   * `kind`, кроме `readonly`.
   */
  setValue?: (row: TRow, rawValue: string) => TRow;
  /** Колонка входит в подытог блока и в итог таблицы (`sumDecimals` по `accessor`). */
  aggregate?: boolean;
  align?: "left" | "right";
  /** CSS-ширина колонки (`"7rem"`, `"120px"`, `"minmax(0,1fr)"`). */
  width?: string;
};

export type EditableGridGroup<TRow> = {
  id: string;
  title: string;
  rows: TRow[];
};

/** Ошибки строки: id колонки -> сообщение. Пустой объект или `null` — ошибок нет. */
export type RowErrors = Record<string, string>;

export type EditableGridLabels = {
  addRow: string;
  deleteRow: string;
  subtotal: string;
  total: string;
  unsaved: string;
  revertAll: string;
  emptyGroup: string;
};

export type EditableGridProps<TRow> = {
  /** «Сохранённое» состояние — источник истины. Смена ссылки сбрасывает черновик. */
  groups: EditableGridGroup<TRow>[];
  columns: EditableGridColumn<TRow>[];
  rowId: (row: TRow) => string;
  /** Вызывается на каждый коммит правки/добавления/удаления с каноничными данными. */
  onChange: (groups: EditableGridGroup<TRow>[]) => void;
  /** Заготовка новой строки для кнопки «добавить строку» в группе. */
  createRow: (groupId: string) => TRow;
  validateRow?: (row: TRow) => RowErrors | null;
  labels?: Partial<EditableGridLabels>;
  /**
   * Только просмотр: ни правки ячеек, ни добавления/удаления строк, ни индикатора
   * несохранённого. Подытоги и итог показываются. Потребитель на экране расчёта КП
   * включает это, когда расчёт вышел из статуса «Черновик» и стал неизменяемым
   * (`docs/spec/10-crm.md` §4.3).
   */
  readOnly?: boolean;
};
