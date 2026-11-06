"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { Badge } from "@/components/ui/badge";
import type { DataTableColumnMeta } from "@/components/data-table/data-table";
import { formatDate } from "@/lib/format/ru";
import { ItemStatus, ItemType, type ItemListItem } from "@/lib/api/endpoints";

export const ITEM_TYPE_LABELS: Record<string, string> = {
  [ItemType.product]: "Изделие",
  [ItemType.material]: "Материал",
  [ItemType.service]: "Услуга",
};

export const ITEM_STATUS_LABELS: Record<string, string> = {
  [ItemStatus.draft]: "Черновик",
  [ItemStatus.active]: "Активен",
  [ItemStatus.archived]: "Архив",
};

const STATUS_VARIANT: Record<string, "secondary" | "default" | "destructive" | "outline"> = {
  [ItemStatus.draft]: "outline",
  [ItemStatus.active]: "default",
  [ItemStatus.archived]: "secondary",
};

export const itemColumns: ColumnDef<ItemListItem, unknown>[] = [
  {
    id: "code",
    accessorKey: "code",
    header: "Код",
    size: 140,
    meta: { orderingKey: "code" } satisfies DataTableColumnMeta,
    cell: ({ row }) => <span className="font-medium">{row.original.code}</span>,
  },
  {
    id: "name",
    accessorKey: "name",
    header: "Наименование",
    meta: { orderingKey: "name" } satisfies DataTableColumnMeta,
  },
  {
    id: "item_type",
    accessorKey: "item_type",
    header: "Тип",
    size: 130,
    cell: ({ row }) => ITEM_TYPE_LABELS[row.original.item_type] ?? row.original.item_type,
  },
  {
    id: "base_uom",
    accessorKey: "base_uom",
    header: "Ед. изм.",
    size: 100,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Статус",
    size: 130,
    cell: ({ row }) => (
      <Badge variant={STATUS_VARIANT[row.original.status] ?? "outline"}>
        {ITEM_STATUS_LABELS[row.original.status] ?? row.original.status}
      </Badge>
    ),
  },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Создан",
    size: 120,
    meta: { orderingKey: "created_at", align: "right" } satisfies DataTableColumnMeta,
    cell: ({ row }) => <span className="tabular-nums">{formatDate(row.original.created_at)}</span>,
  },
];
