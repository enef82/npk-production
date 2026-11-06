"use client";

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Plus, Trash2, Undo2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { formatDecimalRu, parseDecimalInput, roundMoney, sumDecimals } from "./decimal";
import type {
  EditableGridColumn,
  EditableGridGroup,
  EditableGridLabels,
  EditableGridProps,
  RowErrors,
} from "./types";

const DEFAULT_LABELS: EditableGridLabels = {
  addRow: "Добавить строку",
  deleteRow: "Удалить строку",
  subtotal: "Подытог",
  total: "Итого",
  unsaved: "Есть несохранённые изменения",
  revertAll: "Отменить все изменения",
  emptyGroup: "Строк нет",
};

const INVALID_NUMBER = "Введите число";

type CellAddr = { rowId: string; colId: string };

// Separator is an escaped U+0000, not a literal NUL byte in the source: a literal
// NUL makes git treat the file as binary (no diff, no blame). A control char inside
// the key itself is safe here -- row/column ids never contain one.
const addrKey = (a: CellAddr) => `${a.rowId}\u0000${a.colId}`;
const sameCell = (a: CellAddr | null, b: CellAddr | null) =>
  a !== null && b !== null && a.rowId === b.rowId && a.colId === b.colId;

/**
 * Сигнатура данных для определения «есть несохранённое»: id блоков и строк плюс
 * значения всех колонок через `accessor`. Строки — непрозрачные `TRow`, сравнивать
 * их напрямую нельзя, а вот проекция через колонки — ровно то, что видит пользователь.
 */
function signature<TRow>(
  groups: EditableGridGroup<TRow>[],
  columns: EditableGridColumn<TRow>[],
  rowId: (row: TRow) => string,
): string {
  return groups
    .map(
      (group) =>
        `${group.id}` +
        group.rows
          .map(
            (row) =>
              `${rowId(row)}` +
              columns.map((column) => column.accessor(row)).join(""),
          )
          .join(""),
    )
    .join("");
}

function displayValue<TRow>(column: EditableGridColumn<TRow>, row: TRow): string {
  const raw = column.accessor(row);
  if (raw === "") return "";
  if (column.kind === "money") return formatDecimalRu(raw, { minFractionDigits: 2 });
  if (column.kind === "decimal") return formatDecimalRu(raw);
  return raw;
}

function aggregateText<TRow>(column: EditableGridColumn<TRow>, rows: TRow[]): string {
  return formatDecimalRu(
    sumDecimals(rows.map((row) => column.accessor(row))),
    { minFractionDigits: column.kind === "money" ? 2 : 0 },
  );
}

export function EditableGrid<TRow>({
  groups,
  columns,
  rowId,
  onChange,
  createRow,
  validateRow,
  labels,
  readOnly = false,
}: EditableGridProps<TRow>) {
  const text = { ...DEFAULT_LABELS, ...labels };

  // Черновик = рабочая копия. `groups` — «сохранённое»; смена его ссылки (родитель
  // персистнул) сбрасывает черновик. Приём из React-доков «Resetting state with a key»,
  // но на уровне значения, а не key всего компонента.
  const [savedGroups, setSavedGroups] = useState(groups);
  const [draft, setDraft] = useState(groups);
  if (groups !== savedGroups) {
    setSavedGroups(groups);
    setDraft(groups);
  }

  const baselineSignature = useMemo(
    () => signature(savedGroups, columns, rowId),
    [savedGroups, columns, rowId],
  );
  const draftSignature = useMemo(
    () => signature(draft, columns, rowId),
    [draft, columns, rowId],
  );
  const isDirty = draftSignature !== baselineSignature;

  const [editing, setEditing] = useState<CellAddr | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [focused, setFocused] = useState<CellAddr | null>(null);

  const cellRefs = useRef(new Map<string, HTMLDivElement>());
  const inputRef = useRef<HTMLInputElement>(null);
  const suppressBlurCommit = useRef(false);
  const caretMode = useRef<"select" | "end">("select");

  const editableColumnIds = useMemo(
    () =>
      readOnly
        ? []
        : columns.filter((column) => column.kind !== "readonly" && column.setValue).map((c) => c.id),
    [columns, readOnly],
  );
  const flatRowIds = useMemo(
    () => draft.flatMap((group) => group.rows.map(rowId)),
    [draft, rowId],
  );

  const rovingAddr: CellAddr | null =
    (focused && flatRowIds.includes(focused.rowId) && focused) ||
    (flatRowIds.length > 0 && editableColumnIds.length > 0
      ? { rowId: flatRowIds[0], colId: editableColumnIds[0] }
      : null);

  const rowErrors = useMemo(() => {
    const map = new Map<string, RowErrors>();
    if (!validateRow) return map;
    for (const group of draft) {
      for (const row of group.rows) {
        const errors = validateRow(row);
        if (errors && Object.keys(errors).length > 0) map.set(rowId(row), errors);
      }
    }
    return map;
  }, [draft, validateRow, rowId]);

  // --- tanstack/react-table: модель колонок и шапка. Тело рисуем сами (редакторы),
  //     но заголовки и порядок колонок идут через таблицу — точка роста под будущие
  //     фичи (сортировка, скрытие колонок) без переписывания разметки.
  const tableColumns = useMemo<ColumnDef<TRow, unknown>[]>(
    () =>
      columns.map((column) => ({
        id: column.id,
        header: column.header,
        accessorFn: (row: TRow) => column.accessor(row),
      })),
    [columns],
  );
  const tableData = useMemo(() => draft.flatMap((group) => group.rows), [draft]);
  const table = useReactTable({
    data: tableData,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => rowId(row),
  });

  const gridTemplateColumns =
    columns.map((column) => column.width ?? "minmax(6rem, 1fr)").join(" ") + " 2.75rem";

  function findRow(id: string): TRow | null {
    for (const group of draft) {
      for (const row of group.rows) {
        if (rowId(row) === id) return row;
      }
    }
    return null;
  }

  function commitGroups(next: EditableGridGroup<TRow>[]) {
    setDraft(next);
    onChange(next);
  }

  function focusCell(addr: CellAddr | null) {
    if (!addr) return;
    setFocused(addr);
    requestAnimationFrame(() => cellRefs.current.get(addrKey(addr))?.focus());
  }

  /** Возвращает `false`, если значение невалидно — тогда правка остаётся открытой. */
  function commitEdit(): boolean {
    if (!editing) return true;
    const column = columns.find((c) => c.id === editing.colId);
    const row = findRow(editing.rowId);
    if (!column || !column.setValue || !row) {
      setEditing(null);
      return true;
    }

    let rawValue = editValue;
    if (column.kind === "decimal" || column.kind === "money") {
      const parsed = parseDecimalInput(editValue);
      if (parsed === null) {
        setEditError(INVALID_NUMBER);
        return false;
      }
      // Деньги квантуются до копейки на КАЖДОЙ строке — так же, как `line_total`
      // в `src/crm/calculations.py`; сумма уже квантованных строк точна.
      rawValue = column.kind === "money" ? roundMoney(parsed) : parsed;
    }

    const nextRow = column.setValue(row, rawValue);
    const editedId = editing.rowId;
    commitGroups(
      draft.map((group) => ({
        ...group,
        rows: group.rows.map((r) => (rowId(r) === editedId ? nextRow : r)),
      })),
    );
    setEditing(null);
    setEditError(null);
    return true;
  }

  function startEdit(addr: CellAddr, initial?: string) {
    const column = columns.find((c) => c.id === addr.colId);
    if (!column || column.kind === "readonly" || !column.setValue) return;
    if (editing && !sameCell(editing, addr) && !commitEdit()) return;
    const row = findRow(addr.rowId);
    if (!row) return;
    caretMode.current = initial === undefined ? "select" : "end";
    setFocused(addr);
    setEditing(addr);
    setEditError(null);
    setEditValue(initial ?? column.accessor(row));
  }

  function cancelEdit() {
    const addr = editing;
    suppressBlurCommit.current = true;
    setEditing(null);
    setEditError(null);
    requestAnimationFrame(() => {
      if (addr) cellRefs.current.get(addrKey(addr))?.focus();
      suppressBlurCommit.current = false;
    });
  }

  function moveFocus(from: CellAddr, direction: "up" | "down" | "left" | "right" | "next" | "prev") {
    const rowIndex = flatRowIds.indexOf(from.rowId);
    const colIndex = editableColumnIds.indexOf(from.colId);
    if (rowIndex < 0 || colIndex < 0) return;

    let nextRowIndex = rowIndex;
    let nextColIndex = colIndex;
    if (direction === "right") nextColIndex += 1;
    else if (direction === "left") nextColIndex -= 1;
    else if (direction === "down") nextRowIndex += 1;
    else if (direction === "up") nextRowIndex -= 1;
    else if (direction === "next") {
      nextColIndex += 1;
      if (nextColIndex >= editableColumnIds.length) {
        nextColIndex = 0;
        nextRowIndex += 1;
      }
    } else if (direction === "prev") {
      nextColIndex -= 1;
      if (nextColIndex < 0) {
        nextColIndex = editableColumnIds.length - 1;
        nextRowIndex -= 1;
      }
    }

    nextRowIndex = Math.min(Math.max(nextRowIndex, 0), flatRowIds.length - 1);
    nextColIndex = Math.min(Math.max(nextColIndex, 0), editableColumnIds.length - 1);
    focusCell({ rowId: flatRowIds[nextRowIndex], colId: editableColumnIds[nextColIndex] });
  }

  function onCellKeyDown(event: React.KeyboardEvent, addr: CellAddr) {
    switch (event.key) {
      case "ArrowRight":
        event.preventDefault();
        moveFocus(addr, "right");
        break;
      case "ArrowLeft":
        event.preventDefault();
        moveFocus(addr, "left");
        break;
      case "ArrowDown":
        event.preventDefault();
        moveFocus(addr, "down");
        break;
      case "ArrowUp":
        event.preventDefault();
        moveFocus(addr, "up");
        break;
      case "Home":
        event.preventDefault();
        focusCell({ rowId: addr.rowId, colId: editableColumnIds[0] });
        break;
      case "End":
        event.preventDefault();
        focusCell({ rowId: addr.rowId, colId: editableColumnIds[editableColumnIds.length - 1] });
        break;
      case "Enter":
      case "F2":
        event.preventDefault();
        startEdit(addr);
        break;
      default:
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          event.preventDefault();
          startEdit(addr, event.key);
        }
    }
  }

  function onInputKeyDown(event: React.KeyboardEvent) {
    if (!editing) return;
    if (event.key === "Enter") {
      event.preventDefault();
      const addr = editing;
      if (commitEdit()) focusCell(addr);
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelEdit();
    } else if (event.key === "Tab") {
      event.preventDefault();
      const addr = editing;
      if (commitEdit()) moveFocus(addr, event.shiftKey ? "prev" : "next");
    }
  }

  // Самый частый выход из ячейки — клик мимо. Blur коммитит введённое, а не теряет его.
  function onInputBlur() {
    if (suppressBlurCommit.current) return;
    commitEdit();
  }

  function addRow(groupId: string) {
    const row = createRow(groupId);
    commitGroups(
      draft.map((group) =>
        group.id === groupId ? { ...group, rows: [...group.rows, row] } : group,
      ),
    );
    if (editableColumnIds.length > 0) {
      focusCell({ rowId: rowId(row), colId: editableColumnIds[0] });
    }
  }

  function deleteRow(id: string) {
    if (editing?.rowId === id) setEditing(null);
    commitGroups(
      draft.map((group) => ({
        ...group,
        rows: group.rows.filter((row) => rowId(row) !== id),
      })),
    );
  }

  function revertAll() {
    setEditing(null);
    setEditError(null);
    commitGroups(savedGroups);
  }

  useLayoutEffect(() => {
    if (!editing || !inputRef.current) return;
    const input = inputRef.current;
    input.focus();
    if (caretMode.current === "select") input.select();
    else input.setSelectionRange(input.value.length, input.value.length);
  }, [editing]);

  return (
    <div className="flex flex-col gap-2" data-testid="editable-grid">
      {!readOnly && (
        <div className="flex min-h-8 items-center justify-between gap-2">
          <span
            className={cn("text-sm font-medium text-amber-600", !isDirty && "invisible")}
            data-testid="editable-grid-dirty"
            aria-hidden={!isDirty}
          >
            {text.unsaved}
          </span>
          {isDirty && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={revertAll}
              data-testid="editable-grid-revert"
            >
              <Undo2 />
              {text.revertAll}
            </Button>
          )}
        </div>
      )}

      <div role="table" className="overflow-x-auto rounded-md border text-sm">
        <div
          role="row"
          className="grid border-b bg-muted/40 text-xs font-medium text-muted-foreground"
          style={{ gridTemplateColumns }}
        >
          {table.getFlatHeaders().map((header) => {
            const column = columns.find((c) => c.id === header.column.id);
            return (
              <div
                key={header.id}
                role="columnheader"
                className={cn("px-2 py-2", column?.align === "right" && "text-right")}
              >
                {flexRender(header.column.columnDef.header, header.getContext())}
              </div>
            );
          })}
          <div role="columnheader" aria-label={text.deleteRow} />
        </div>

        {draft.map((group) => (
          <div key={group.id} role="rowgroup" data-testid={`eg-group-${group.id}`}>
            <div
              role="row"
              className="grid border-b bg-muted/60 px-2 py-1.5 font-medium"
              data-testid={`eg-group-title-${group.id}`}
            >
              {group.title}
            </div>

            {group.rows.length === 0 && (
              <div className="border-b px-2 py-2 text-muted-foreground">{text.emptyGroup}</div>
            )}

            {group.rows.map((row) => {
              const id = rowId(row);
              const errors = rowErrors.get(id);
              return (
                <div key={id} className="border-b">
                  <div
                    role="row"
                    className="grid"
                    style={{ gridTemplateColumns }}
                    data-testid={`eg-row-${id}`}
                  >
                    {columns.map((column) => {
                      const addr: CellAddr = { rowId: id, colId: column.id };
                      const editable = !readOnly && column.kind !== "readonly" && !!column.setValue;
                      const isEditing = sameCell(editing, addr);
                      const isRoving = sameCell(rovingAddr, addr);
                      const cellError = errors?.[column.id];
                      return (
                        <div
                          key={column.id}
                          role="cell"
                          data-testid={`eg-cell-${id}-${column.id}`}
                          ref={(element) => {
                            if (element) cellRefs.current.set(addrKey(addr), element);
                            else cellRefs.current.delete(addrKey(addr));
                          }}
                          tabIndex={editable && !isEditing && isRoving ? 0 : -1}
                          onFocus={() => {
                            if (editable && !isEditing) setFocused(addr);
                          }}
                          onKeyDown={(event) => {
                            if (editable && !isEditing) onCellKeyDown(event, addr);
                          }}
                          onClick={() => {
                            if (editable && !isEditing) startEdit(addr);
                          }}
                          data-invalid={cellError ? "" : undefined}
                          className={cn(
                            "min-w-0 px-2 py-1 outline-none",
                            column.align === "right" && "text-right tabular-nums",
                            editable && "cursor-text",
                            isRoving && !isEditing && "ring-1 ring-inset ring-ring",
                            cellError && "bg-destructive/10",
                          )}
                        >
                          {isEditing ? (
                            <Input
                              ref={inputRef}
                              data-testid={`eg-input-${id}-${column.id}`}
                              value={editValue}
                              inputMode={column.kind === "text" ? "text" : "decimal"}
                              onChange={(event) => setEditValue(event.target.value)}
                              onKeyDown={onInputKeyDown}
                              onBlur={onInputBlur}
                              aria-invalid={editError ? true : undefined}
                              aria-label={column.header}
                              className={cn(
                                "h-6 px-1 py-0 text-sm",
                                column.align === "right" && "text-right",
                              )}
                            />
                          ) : (
                            <span className="block truncate">{displayValue(column, row)}</span>
                          )}
                        </div>
                      );
                    })}
                    <div role="cell" className="flex items-center justify-center">
                      {!readOnly && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          onClick={() => deleteRow(id)}
                          data-testid={`eg-del-${id}`}
                          aria-label={text.deleteRow}
                        >
                          <Trash2 />
                        </Button>
                      )}
                    </div>
                  </div>

                  {errors && (
                    <div
                      role="alert"
                      className="px-2 pb-1 text-xs text-destructive"
                      data-testid={`eg-error-${id}`}
                    >
                      {Object.values(errors).join("; ")}
                    </div>
                  )}
                </div>
              );
            })}

            <div
              role="row"
              className="grid border-b bg-muted/30 font-medium"
              style={{ gridTemplateColumns }}
              data-testid={`eg-subtotal-row-${group.id}`}
            >
              {columns.map((column, index) => (
                <div
                  key={column.id}
                  className={cn(
                    "px-2 py-1.5",
                    column.align === "right" && "text-right tabular-nums",
                  )}
                >
                  {index === 0 ? (
                    text.subtotal
                  ) : column.aggregate ? (
                    <span data-testid={`eg-subtotal-${group.id}-${column.id}`}>
                      {aggregateText(column, group.rows)}
                    </span>
                  ) : null}
                </div>
              ))}
              <div />
            </div>

            {!readOnly && (
              <div className="border-b px-2 py-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => addRow(group.id)}
                  data-testid={`eg-add-${group.id}`}
                >
                  <Plus />
                  {text.addRow}
                </Button>
              </div>
            )}
          </div>
        ))}

        <div
          role="row"
          className="grid bg-muted/50 font-semibold"
          style={{ gridTemplateColumns }}
          data-testid="eg-total-row"
        >
          {columns.map((column, index) => (
            <div
              key={column.id}
              className={cn("px-2 py-2", column.align === "right" && "text-right tabular-nums")}
            >
              {index === 0 ? (
                text.total
              ) : column.aggregate ? (
                <span data-testid={`eg-total-${column.id}`}>
                  {aggregateText(column, tableData)}
                </span>
              ) : null}
            </div>
          ))}
          <div />
        </div>
      </div>
    </div>
  );
}
