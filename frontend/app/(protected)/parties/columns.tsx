"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { Badge } from "@/components/ui/badge";
import type { DataTableColumnMeta } from "@/components/data-table/data-table";
import { formatDate } from "@/lib/format/ru";
import { PartyStatus, PartyType, type PartyListItem } from "@/lib/api/endpoints";

export const PARTY_TYPE_LABELS: Record<string, string> = {
  [PartyType.legal]: "Юр. лицо",
  [PartyType.entrepre]: "ИП",
  [PartyType.person]: "Физ. лицо",
  [PartyType.foreign]: "Нерезидент",
};

export const PARTY_STATUS_LABELS: Record<string, string> = {
  [PartyStatus.draft]: "Черновик",
  [PartyStatus.active]: "Активен",
  [PartyStatus.blocked]: "Заблокирован",
  [PartyStatus.archived]: "Архив",
};

const STATUS_VARIANT: Record<string, "secondary" | "default" | "destructive" | "outline"> = {
  [PartyStatus.draft]: "outline",
  [PartyStatus.active]: "default",
  [PartyStatus.blocked]: "destructive",
  [PartyStatus.archived]: "secondary",
};

export const partyColumns: ColumnDef<PartyListItem, unknown>[] = [
  {
    id: "short_name",
    accessorKey: "short_name",
    header: "Наименование",
    meta: { orderingKey: "short_name" } satisfies DataTableColumnMeta,
    cell: ({ row }) => <span className="font-medium">{row.original.short_name}</span>,
  },
  {
    id: "inn",
    accessorKey: "inn",
    header: "ИНН",
    size: 140,
    cell: ({ row }) => row.original.inn || "—",
  },
  {
    id: "party_type",
    accessorKey: "party_type",
    header: "Тип",
    size: 130,
    cell: ({ row }) => PARTY_TYPE_LABELS[row.original.party_type] ?? row.original.party_type,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Статус",
    size: 140,
    cell: ({ row }) => (
      <Badge variant={STATUS_VARIANT[row.original.status] ?? "outline"}>
        {PARTY_STATUS_LABELS[row.original.status] ?? row.original.status}
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
