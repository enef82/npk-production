"use client";

import { useEffect } from "react";

/**
 * Предупреждение о несохранённых изменениях. Надёжно ловит закрытие вкладки и
 * обновление страницы (`beforeunload`) — переходы между внутренними страницами
 * приложения (Link/router.push) в App Router перехватить так же централизованно
 * нельзя без собственного роутера поверх Next.js; сознательно не притворяемся,
 * что это покрыто, а не тихо оставляем дыру.
 */
export function useUnsavedChangesGuard(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return;
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);
}
