"use client";

import { useState } from "react";

import { DataTable } from "@/components/data-table/data-table";
import { exportRowsToExcel } from "@/components/data-table/export-excel";
import { useKnownTotal } from "@/components/data-table/use-known-total";
import { useTableUrlState } from "@/components/data-table/use-table-url-state";
import { listItems, useListItems, type ListItemsParams } from "@/lib/api/endpoints";
import { toast } from "sonner";

import { ITEM_STATUS_LABELS, ITEM_TYPE_LABELS, itemColumns } from "./columns";
import { ItemsToolbar } from "./items-toolbar";

const EXPORT_PAGE_SIZE = 100;
const EXPORT_ROW_LIMIT = 5000;

export function ItemsView() {
  const urlState = useTableUrlState("", 20);
  const [isExporting, setIsExporting] = useState(false);

  const params: ListItemsParams = {
    search: urlState.search || undefined,
    item_type: (urlState.filters.item_type as ListItemsParams["item_type"]) || undefined,
    status: (urlState.filters.status as ListItemsParams["status"]) || undefined,
    cursor: urlState.cursor || undefined,
    page_size: urlState.pageSize,
    ordering: urlState.ordering || undefined,
    with_total: !urlState.cursor,
  };

  const query = useListItems(params, { query: { placeholderData: (prev) => prev } });
  const { total, totalCap } = useKnownTotal(query.data);

  async function handleExport() {
    setIsExporting(true);
    try {
      const rows: Record<string, string>[] = [];
      let cursor: string | null | undefined;
      do {
        const page = await listItems({ ...params, cursor: cursor ?? undefined, page_size: EXPORT_PAGE_SIZE });
        for (const item of page.items) {
          rows.push({
            code: item.code,
            name: item.name,
            item_type: ITEM_TYPE_LABELS[item.item_type] ?? item.item_type,
            base_uom: item.base_uom,
            status: ITEM_STATUS_LABELS[item.status] ?? item.status,
            created_at: item.created_at,
          });
        }
        cursor = page.next_cursor;
      } while (cursor && rows.length < EXPORT_ROW_LIMIT);

      await exportRowsToExcel(
        "nomenklatura",
        [
          { key: "code", label: "Код", width: 16 },
          { key: "name", label: "Наименование", width: 36 },
          { key: "item_type", label: "Тип", width: 16 },
          { key: "base_uom", label: "Ед. изм.", width: 12 },
          { key: "status", label: "Статус", width: 16 },
          { key: "created_at", label: "Создан", width: 20 },
        ],
        rows,
      );
    } catch {
      toast.error("Не удалось выполнить экспорт.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <h1 className="text-lg font-semibold">Номенклатура</h1>

      <DataTable
        columns={itemColumns}
        data={query.data?.items ?? []}
        rowId={(item) => item.id}
        isLoading={query.isLoading}
        isFetching={query.isFetching}
        nextCursor={query.data?.next_cursor}
        total={total}
        totalCap={totalCap}
        urlState={urlState}
        toolbar={<ItemsToolbar urlState={urlState} />}
        onExport={handleExport}
        isExporting={isExporting}
        emptyMessage="Номенклатура не найдена."
      />
    </div>
  );
}
