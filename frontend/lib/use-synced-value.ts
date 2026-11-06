"use client";

import { useState } from "react";

/**
 * Локальное значение поля ввода, управляемое (controlled) и синхронизированное
 * с сервером. Заменяет паттерн `defaultValue` + `key={...}` (шаг 18): тот не
 * связывает ввод со state, поэтому набранное остаётся в DOM и не уходит на
 * сервер (`docs/plan-ustraneniya-zamechaniy-1a.md`, группа 1.1а) — обнаружено
 * на наценке блока, тот же дефект был и у места отгрузки, и у срока блока.
 *
 * При изменении `serverValue` (успешное сохранение, `invalidateQueries`) локальное
 * значение сбрасывается на него — тот же приём «сравнение при рендере», что уже
 * применён к графику платежей (`savedDraft`/`savedRef` в `commercial-terms-panel.tsx`),
 * а не `useEffect`: React явно рекомендует этот способ сброса state по смене пропса.
 */
export function useSyncedValue<T>(serverValue: T): [T, (value: T) => void] {
  const [value, setValue] = useState(serverValue);
  const [syncedFrom, setSyncedFrom] = useState(serverValue);
  if (serverValue !== syncedFrom) {
    setSyncedFrom(serverValue);
    setValue(serverValue);
  }
  return [value, setValue];
}
