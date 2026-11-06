"use client";

import { useEffect, useState } from "react";

/**
 * `false` на сервере и на первом клиентском рендере, `true` после гидратации.
 *
 * Нужен, чтобы блокировать управляемые поля ввода до того, как React привяжет
 * `onChange`: до этого момента браузер принимает нажатия, а обработчик их не видит —
 * текст молча теряется (а при гидратации управляемый инпут ещё и сбрасывается к
 * значению из состояния). Заблокированное поле честно показывает «ещё не готово».
 */
export function useHydrated(): boolean {
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);
  return hydrated;
}
