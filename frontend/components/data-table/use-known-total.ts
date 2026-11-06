"use client";

import { useEffect, useState } from "react";

type WithTotal = { total?: number | null; total_cap?: number | null };

/**
 * Backend считает `total` только по запросу (`with_total=1`, первая страница набора —
 * см. `_add_total` в `core/identity/api/routers.py`); при переходе «Далее» полей
 * total/total_cap в ответе вообще нет. Хук держит последнее известное значение, пока
 * не сменится фильтр/сортировка и не придёт новый ответ с total_cap — иначе счётчик
 * находок пропадал бы на второй странице.
 */
export function useKnownTotal(data: WithTotal | undefined): { total?: number | null; totalCap?: number | null } {
  const [known, setKnown] = useState<{ total: number | null; totalCap: number } | null>(null);

  useEffect(() => {
    if (data && data.total_cap !== undefined && data.total_cap !== null) {
      setKnown({ total: data.total ?? null, totalCap: data.total_cap });
    }
  }, [data]);

  return known ? { total: known.total, totalCap: known.totalCap } : {};
}
