"use client";

import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ItemStatus, ItemType } from "@/lib/api/endpoints";
import { useHydrated } from "@/lib/use-hydrated";
import type { TableUrlActions, TableUrlState } from "@/components/data-table/use-table-url-state";
import { ITEM_STATUS_LABELS, ITEM_TYPE_LABELS } from "./columns";

export function ItemsToolbar({ urlState }: { urlState: TableUrlState & TableUrlActions }) {
  const hydrated = useHydrated();
  const [searchDraft, setSearchDraft] = useState(urlState.search);

  useEffect(() => setSearchDraft(urlState.search), [urlState.search]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (searchDraft !== urlState.search) urlState.setSearch(searchDraft);
    }, 300);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchDraft]);

  return (
    <>
      <Input
        value={searchDraft}
        onChange={(event) => setSearchDraft(event.target.value)}
        placeholder="Поиск по коду, наименованию…"
        className="h-9 max-w-64"
        aria-label="Поиск по номенклатуре"
        // до гидратации onChange не привязан — заблокировано, чтобы ввод не терялся молча
        disabled={!hydrated}
      />

      <Select
        value={urlState.filters.item_type ?? "all"}
        onValueChange={(value) => urlState.setFilter("item_type", value === "all" ? null : value)}
      >
        <SelectTrigger size="sm" className="w-40" aria-label="Тип номенклатуры">
          <SelectValue>
            {(value: string | null) => (value && value !== "all" ? ITEM_TYPE_LABELS[value] : "Все типы")}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Все типы</SelectItem>
          {Object.values(ItemType).map((type) => (
            <SelectItem key={type} value={type}>
              {ITEM_TYPE_LABELS[type]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={urlState.filters.status ?? "all"}
        onValueChange={(value) => urlState.setFilter("status", value === "all" ? null : value)}
      >
        <SelectTrigger size="sm" className="w-40" aria-label="Статус">
          <SelectValue>
            {(value: string | null) => (value && value !== "all" ? ITEM_STATUS_LABELS[value] : "Все статусы")}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Все статусы</SelectItem>
          {Object.values(ItemStatus).map((status) => (
            <SelectItem key={status} value={status}>
              {ITEM_STATUS_LABELS[status]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </>
  );
}
