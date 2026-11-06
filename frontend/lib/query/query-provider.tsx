"use client";

import { useState } from "react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/mutator";

/**
 * Единая обработка ошибок (задание, п.3): любая ошибка запроса/мутации превращается
 * в тост автоматически, если сама мутация не попросила промолчать через
 * `meta: { skipGlobalErrorToast: true }` — так помечает себя EntityForm, когда сама
 * показывает ошибку рядом с полем или диалогом дублей, чтобы не дублировать тост.
 *
 * 401 — особый случай (обработка истечения сессии, задание п.2): сессия истекла или
 * не установлена, тост плюс жёсткий переход на /login с `next`, чтобы после
 * повторного входа пользователь вернулся туда, где был. Жёсткий redirect (не
 * router.push), потому что колбэк кэша живёт вне дерева React и не имеет доступа
 * к router; это и не проблема — истёкшая сессия всё равно требует чистого состояния.
 */
function handleError(error: unknown, skipToast: boolean | undefined): void {
  if (skipToast) return;

  if (error instanceof ApiError && error.status === 401) {
    toast.error("Сессия истекла", { description: "Войдите снова, чтобы продолжить." });
    if (typeof window !== "undefined") {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?next=${next}`;
    }
    return;
  }

  const message = error instanceof ApiError ? error.message : "Не удалось выполнить запрос.";
  toast.error(message);
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status < 500) return false;
          return failureCount < 2;
        },
      },
    },
    queryCache: new QueryCache({
      onError: (error, query) => handleError(error, query.meta?.skipGlobalErrorToast as boolean | undefined),
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) =>
        handleError(error, mutation.meta?.skipGlobalErrorToast as boolean | undefined),
    }),
  });
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(createQueryClient);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
