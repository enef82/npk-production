"use client";

import { useEffect, useRef } from "react";
import type { FieldValues, UseFormReturn } from "react-hook-form";

const DRAFT_PREFIX = "entity-form-draft:";

export function readDraft<TValues>(draftKey: string): TValues | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(DRAFT_PREFIX + draftKey);
    return raw ? (JSON.parse(raw) as TValues) : null;
  } catch {
    return null;
  }
}

function clearDraft(draftKey: string): void {
  window.localStorage.removeItem(DRAFT_PREFIX + draftKey);
}

/**
 * Автосохранение черновика формы в localStorage, debounced. Восстановление — на
 * вызывающей стороне через `readDraft` до рендера формы (передаётся в
 * `defaultValues`), а не здесь: react-hook-form не любит менять defaultValues
 * форм уже после инициализации.
 */
export function useDraftAutosave<TValues extends FieldValues>(
  draftKey: string | undefined,
  form: UseFormReturn<TValues>,
): { clearDraft: () => void } {
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!draftKey) return;
    const subscription = form.watch((values) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        window.localStorage.setItem(DRAFT_PREFIX + draftKey, JSON.stringify(values));
      }, 500);
    });
    return () => {
      subscription.unsubscribe();
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);

  return { clearDraft: () => draftKey && clearDraft(draftKey) };
}
