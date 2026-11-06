"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type BreadcrumbLabels = Record<string, string>;
type BreadcrumbLabelsContextValue = {
  labels: BreadcrumbLabels;
  setLabel: (segment: string, label: string | undefined) => void;
};

const BreadcrumbLabelsContext = createContext<BreadcrumbLabelsContextValue | null>(null);

export function BreadcrumbLabelsProvider({ children }: { children: React.ReactNode }) {
  const [labels, setLabels] = useState<BreadcrumbLabels>({});

  // `useCallback` с пустыми deps — принципиально: `setLabel` не должна меняться при
  // каждом изменении `labels`, иначе `useDynamicBreadcrumbLabel` ниже (у которой
  // `setLabel` в зависимостях эффекта) перезапускает эффект на каждое собственное же
  // изменение `labels` → бесконечный цикл рендеров (снять метку → labels меняется →
  // новый setLabel → эффект перезапускается → поставить метку → labels опять меняется…).
  const setLabel = useCallback((segment: string, label: string | undefined) => {
    setLabels((prev) => {
      if (label === undefined) {
        if (!(segment in prev)) return prev;
        return Object.fromEntries(Object.entries(prev).filter(([key]) => key !== segment));
      }
      if (prev[segment] === label) return prev;
      return { ...prev, [segment]: label };
    });
  }, []);

  const value = useMemo<BreadcrumbLabelsContextValue>(() => ({ labels, setLabel }), [labels, setLabel]);

  return <BreadcrumbLabelsContext.Provider value={value}>{children}</BreadcrumbLabelsContext.Provider>;
}

export function useBreadcrumbLabels(): BreadcrumbLabels {
  const ctx = useContext(BreadcrumbLabelsContext);
  if (!ctx) throw new Error("useBreadcrumbLabels должен вызываться внутри BreadcrumbLabelsProvider.");
  return ctx.labels;
}

/**
 * Динамический сегмент маршрута (например, UUID контрагента) регистрирует своё
 * человекочитаемое имя для хлебных крошек — без этого `Breadcrumbs` показал бы
 * голый UUID вместо «Ромашка ООО». Снимает метку при размонтировании страницы.
 */
export function useDynamicBreadcrumbLabel(segment: string | undefined, label: string | undefined): void {
  const ctx = useContext(BreadcrumbLabelsContext);
  if (!ctx) throw new Error("useDynamicBreadcrumbLabel должен вызываться внутри BreadcrumbLabelsProvider.");
  const { setLabel } = ctx;

  useEffect(() => {
    if (!segment || !label) return;
    setLabel(segment, label);
    return () => setLabel(segment, undefined);
  }, [segment, label, setLabel]);
}
