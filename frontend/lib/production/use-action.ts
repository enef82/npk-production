"use client";

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/mutator";

/**
 * Запуск действия над заказом/заявкой: ошибка сервера — тостом (sonner), успех —
 * необязательный тост и перезапрос данных экранов производства. Одно действие меняет
 * сразу несколько представлений (доска, карточка, Гант, «Мои визы»), поэтому
 * инвалидируются все запросы модулей `production` и `sales` целиком, а не точечно:
 * точечная инвалидация здесь — место для расхождения экранов, а выигрыша почти нет.
 */
export function useAction() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async <T>(fn: () => Promise<T>, success?: string | ((result: T) => string | undefined)): Promise<T | undefined> => {
      setPending(true);
      try {
        const result = await fn();
        const message = typeof success === "function" ? success(result) : success;
        if (message) toast.success(message);
        return result;
      } catch (error) {
        toast.error(error instanceof ApiError ? error.message : "Не удалось выполнить действие.");
        return undefined;
      } finally {
        setPending(false);
        await queryClient.invalidateQueries({
          predicate: (query) => {
            const key = query.queryKey[0];
            return typeof key === "string" && (key.startsWith("/api/v1/production") || key.startsWith("/api/v1/sales"));
          },
        });
      }
    },
    [queryClient],
  );

  return { run, pending };
}
