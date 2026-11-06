"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type ColumnDef,
  type RowSelectionState,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, Loader2 } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format/ru";
import type { TableUrlActions, TableUrlState } from "./use-table-url-state";

// Плотность и клавиатура — приоритет, не оформление: это экран, за которым сидят
// весь день. ROW_HEIGHT_PX держит строку компактной (больше строк без прокрутки),
// а фокус построчно управляется вручную (roving tabindex) — стрелки вверх/вниз,
// Home/End, Enter — работа без мыши не факультативна.
const ROW_HEIGHT_PX = 36;

export type DataTableColumnMeta = {
  /** Значение параметра `ordering` backend'а для сортировки по возрастанию этой колонки. */
  orderingKey?: string;
  align?: "left" | "right";
};

export type DataTableProps<TData> = {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  rowId: (row: TData) => string;
  isLoading: boolean;
  isFetching?: boolean;
  nextCursor?: string | null;
  /**
   * Точное количество строк по текущим фильтрам — только когда backend его правда
   * посчитал (запрос `with_total=1` на первой странице набора, см. `_add_total` в
   * `core/identity/api/routers.py`). `undefined`, если ещё не пришло. `null` при
   * `totalCap` — значит «больше totalCap», backend отдаёт порог сам, компонент его
   * не хардкодит.
   */
  total?: number | null;
  totalCap?: number | null;
  urlState: TableUrlState & TableUrlActions;
  toolbar?: React.ReactNode;
  emptyMessage?: string;
  enableRowSelection?: boolean;
  onRowActivate?: (row: TData) => void;
  onExport?: () => void;
  isExporting?: boolean;
  exportLabel?: string;
};

function footerText(args: {
  isLoading: boolean;
  isFetching?: boolean;
  total?: number | null;
  totalCap?: number | null;
  rowCount: number;
}): string | null {
  const { isLoading, isFetching, total, totalCap, rowCount } = args;
  if (isFetching && !isLoading) return "Обновление…";
  if (total !== undefined) {
    return total === null ? `Найдено: более ${formatNumber(totalCap)}` : `Найдено: ${formatNumber(total)}`;
  }
  return rowCount > 0 ? `Показано строк: ${rowCount}` : null;
}

export function DataTable<TData>({
  columns,
  data,
  rowId,
  isLoading,
  isFetching,
  nextCursor,
  total,
  totalCap,
  urlState,
  toolbar,
  emptyMessage = "Ничего не найдено.",
  enableRowSelection = false,
  onRowActivate,
  onExport,
  isExporting,
  exportLabel = "Экспорт в Excel",
}: DataTableProps<TData>) {
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const effectiveColumns = useMemo<ColumnDef<TData, unknown>[]>(() => {
    if (!enableRowSelection) return columns;
    const selectColumn: ColumnDef<TData, unknown> = {
      id: "__select",
      size: 36,
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllRowsSelected()}
          indeterminate={table.getIsSomeRowsSelected() && !table.getIsAllRowsSelected()}
          onCheckedChange={(value) => table.toggleAllRowsSelected(!!value)}
          aria-label="Выбрать все строки на странице"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          onClick={(event) => event.stopPropagation()}
          aria-label="Выбрать строку"
        />
      ),
    };
    return [selectColumn, ...columns];
  }, [columns, enableRowSelection]);

  const table = useReactTable({
    data,
    columns: effectiveColumns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: rowId,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    enableRowSelection,
  });

  const rows = table.getRowModel().rows;

  const gridTemplateColumns = effectiveColumns
    .map((column) => (column.size ? `${column.size}px` : "minmax(0, 1fr)"))
    .join(" ");

  const scrollRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: 12,
  });

  // Roving tabindex: только одна строка в tab-порядке одновременно, стрелками
  // перемещаем фокус между строками — обычный Tab перескакивал бы через все строки
  // разом, что на списке в сотни записей не годится ни для скорости, ни для a11y.
  const [focusedIndex, setFocusedIndex] = useState(0);
  const rowRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (focusedIndex >= rows.length) setFocusedIndex(Math.max(0, rows.length - 1));
  }, [rows.length, focusedIndex]);

  const focusRow = useCallback((index: number) => {
    setFocusedIndex(index);
    rowVirtualizer.scrollToIndex(index, { align: "auto" });
    requestAnimationFrame(() => rowRefs.current.get(index)?.focus());
  }, [rowVirtualizer]);

  function handleRowKeyDown(event: React.KeyboardEvent, index: number, row: TData) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusRow(Math.min(index + 1, rows.length - 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        focusRow(Math.max(index - 1, 0));
        break;
      case "Home":
        event.preventDefault();
        focusRow(0);
        break;
      case "End":
        event.preventDefault();
        focusRow(rows.length - 1);
        break;
      case "Enter":
        if (onRowActivate) {
          event.preventDefault();
          onRowActivate(row);
        }
        break;
    }
  }

  return (
    <div className="flex h-full flex-col gap-3">
      {(toolbar || onExport) && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-1 flex-wrap items-center gap-2">{toolbar}</div>
          {onExport && (
            <Button variant="outline" size="sm" onClick={onExport} disabled={isExporting}>
              {isExporting ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Download className="size-4" aria-hidden />
              )}
              {exportLabel}
            </Button>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col rounded-md border">
        <div
          role="table"
          aria-rowcount={rows.length}
          className="grid shrink-0 border-b bg-muted/40 text-xs font-medium text-muted-foreground"
          style={{ gridTemplateColumns }}
        >
          {table.getHeaderGroups().map((headerGroup) =>
            headerGroup.headers.map((header) => {
              const meta = header.column.columnDef.meta as DataTableColumnMeta | undefined;
              const orderingKey = meta?.orderingKey;
              const isSorted = orderingKey && urlState.ordering?.replace(/^-/, "") === orderingKey;
              const isDescending = isSorted && urlState.ordering?.startsWith("-");

              return (
                <div
                  key={header.id}
                  role="columnheader"
                  className={cn(
                    "flex items-center gap-1 px-3 py-2",
                    meta?.align === "right" && "justify-end",
                  )}
                >
                  {header.isPlaceholder ? null : orderingKey ? (
                    <button
                      type="button"
                      className="flex items-center gap-1 rounded hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                      onClick={() =>
                        urlState.setOrdering(isSorted && !isDescending ? `-${orderingKey}` : orderingKey)
                      }
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {isSorted ? (
                        isDescending ? (
                          <ArrowDown className="size-3.5" aria-hidden />
                        ) : (
                          <ArrowUp className="size-3.5" aria-hidden />
                        )
                      ) : (
                        <ArrowUpDown className="size-3.5 opacity-40" aria-hidden />
                      )}
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </div>
              );
            }),
          )}
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
          {isLoading ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 size-4 animate-spin" aria-hidden />
              Загрузка…
            </div>
          ) : rows.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              {emptyMessage}
            </div>
          ) : (
            <div
              role="rowgroup"
              style={{ height: rowVirtualizer.getTotalSize(), position: "relative" }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const row = rows[virtualRow.index];
                return (
                  <div
                    key={row.id}
                    ref={(el) => {
                      if (el) rowRefs.current.set(virtualRow.index, el);
                      else rowRefs.current.delete(virtualRow.index);
                    }}
                    role="row"
                    tabIndex={virtualRow.index === focusedIndex ? 0 : -1}
                    onFocus={() => setFocusedIndex(virtualRow.index)}
                    onKeyDown={(event) => handleRowKeyDown(event, virtualRow.index, row.original)}
                    onClick={() => onRowActivate?.(row.original)}
                    className={cn(
                      "grid items-center border-b px-0 text-sm outline-none",
                      "hover:bg-muted/50 focus-visible:bg-accent focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                      onRowActivate && "cursor-pointer",
                    )}
                    style={{
                      gridTemplateColumns,
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: ROW_HEIGHT_PX,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta as DataTableColumnMeta | undefined;
                      return (
                        <div
                          key={cell.id}
                          role="cell"
                          className={cn("truncate px-3", meta?.align === "right" && "text-right tabular-nums")}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{footerText({ isLoading, isFetching, total, totalCap, rowCount: rows.length })}</span>
        {/* Только «назад/вперёд» — курсорная (keyset) пагинация принципиально не умеет
            прыгать на произвольную страницу; нумерованные «1 2 3 … 18» здесь были бы
            обманом (см. use-table-url-state.ts). Переход к конкретной записи — через
            поиск/фильтр, не через листание. */}
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={urlState.goToPreviousPage}
            disabled={!urlState.canGoBack || isLoading}
          >
            <ChevronLeft className="size-4" aria-hidden />
            Назад
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => nextCursor && urlState.goToNextPage(nextCursor)}
            disabled={!nextCursor || isLoading}
          >
            Далее
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
      </div>
    </div>
  );
}
