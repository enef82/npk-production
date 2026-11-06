"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export type TableUrlState = {
  cursor: string | null;
  ordering: string | null;
  pageSize: number;
  search: string;
  filters: Record<string, string>;
  canGoBack: boolean;
};

export type TableUrlActions = {
  /** Курсор следующей страницы пришёл из ответа API — кладём текущий в стек «назад». */
  goToNextPage: (nextCursor: string) => void;
  goToPreviousPage: () => void;
  setOrdering: (ordering: string | null) => void;
  setPageSize: (pageSize: number) => void;
  setSearch: (search: string) => void;
  setFilter: (key: string, value: string | null) => void;
  reset: () => void;
};

/**
 * Синхронизирует состояние DataTable (курсор + история «назад», сортировка,
 * размер страницы, фильтры) с query-параметрами URL — обновление страницы или
 * прямая ссылка восстанавливают ровно то, что было. `namespace` разделяет
 * параметры нескольких таблиц на одной странице (не нужно сейчас, но не будет
 * коллизий, если понадобится).
 *
 * Курсор — однонаправленный (см. core/common/pagination.py): «назад» не эндпоинт
 * backend'а, а локальный стек посещённых курсоров, тоже сохранённый в URL.
 */
export function useTableUrlState(namespace: string, defaultPageSize = 20): TableUrlState & TableUrlActions {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const key = useCallback((name: string) => (namespace ? `${namespace}_${name}` : name), [namespace]);

  const cursor = searchParams.get(key("cursor"));
  const prevStack = useMemo(
    () => (searchParams.get(key("prev")) ?? "").split(",").filter(Boolean),
    [searchParams, key],
  );
  const ordering = searchParams.get(key("ordering"));
  const pageSize = Number(searchParams.get(key("pageSize"))) || defaultPageSize;
  const search = searchParams.get(key("search")) ?? "";

  const filters = useMemo(() => {
    const prefix = key("f_");
    const result: Record<string, string> = {};
    searchParams.forEach((value, paramKey) => {
      if (paramKey.startsWith(prefix)) result[paramKey.slice(prefix.length)] = value;
    });
    return result;
  }, [searchParams, key]);

  const applyPatch = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [name, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(name);
        else next.set(name, value);
      }
      router.push(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  return {
    cursor,
    ordering,
    pageSize,
    search,
    filters,
    canGoBack: cursor !== null,
    goToNextPage: (nextCursor) =>
      applyPatch({
        [key("cursor")]: nextCursor,
        [key("prev")]: [...prevStack, cursor ?? ""].join(","),
      }),
    goToPreviousPage: () => {
      const stack = [...prevStack];
      const previous = stack.pop() ?? null;
      applyPatch({ [key("cursor")]: previous, [key("prev")]: stack.join(",") });
    },
    setOrdering: (value) =>
      // смена сортировки обнуляет курсор — курсор прошлой сортировки нерелевантен
      // (core/common/pagination.py: несовпадение ключа сортировки в курсоре игнорируется).
      applyPatch({ [key("ordering")]: value, [key("cursor")]: null, [key("prev")]: null }),
    setPageSize: (value) =>
      applyPatch({ [key("pageSize")]: String(value), [key("cursor")]: null, [key("prev")]: null }),
    setSearch: (value) =>
      applyPatch({ [key("search")]: value, [key("cursor")]: null, [key("prev")]: null }),
    setFilter: (filterKey, value) =>
      applyPatch({ [key(`f_${filterKey}`)]: value, [key("cursor")]: null, [key("prev")]: null }),
    reset: () => {
      const next = new URLSearchParams(searchParams.toString());
      for (const paramKey of Array.from(next.keys())) {
        if (paramKey.startsWith(namespace ? `${namespace}_` : "")) next.delete(paramKey);
      }
      router.push(`${pathname}?${next.toString()}`, { scroll: false });
    },
  };
}
