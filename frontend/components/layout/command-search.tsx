"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

/**
 * Глобальный поиск (⌘K) — не отдельный API, переиспользует уже существующий
 * список контрагентов: ввод и Enter ведут на /parties?search=..., сам экран
 * выполняет запрос. Второго поискового эндпоинта на backend нет и не заводился.
 */
export function CommandSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  function submit() {
    const trimmed = query.trim();
    setOpen(false);
    setQuery("");
    router.push(trimmed ? `/parties?search=${encodeURIComponent(trimmed)}` : "/parties");
  }

  return (
    <>
      <Button
        variant="outline"
        className="w-full max-w-xs justify-start gap-2 text-muted-foreground sm:w-64"
        onClick={() => setOpen(true)}
      >
        <Search className="size-4" aria-hidden />
        Поиск контрагентов…
        <kbd className="ml-auto rounded border bg-muted px-1.5 py-0.5 text-xs">⌘K</kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen} title="Поиск" description="Поиск по контрагентам">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Название, ИНН…" value={query} onValueChange={setQuery} />
          <CommandList>
            <CommandEmpty>Нажмите Enter для поиска «{query}»</CommandEmpty>
            {query.trim() && (
              // `onSelect` — единственный обработчик Enter: cmdk сам активирует
              // выделенный CommandItem по Enter, отдельный onKeyDown на CommandInput
              // вызывал submit() ещё раз (двойной вызов гонял query state и терял
              // введённый текст из URL) — обнаружено ручной проверкой в браузере.
              <CommandItem onSelect={submit}>Найти «{query}» среди контрагентов</CommandItem>
            )}
          </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
