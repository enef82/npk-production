"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  createInquiry,
  useListParties,
  useListProductionEmployees,
  useListProductTemplates,
  type InquiryCreateIn,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { addWorkingDays, todayIso } from "@/lib/production/dates";
import { cn } from "@/lib/utils";

import { Field, NativeSelect, TextInput } from "./bits";

type Candidate = { id: string; label: string; inn: string };

/**
 * Новая заявка (§3.2): заказчик — существующий `Party` или новый (создаётся сервисом
 * ядра с проверкой дублей: при похожем сервер отвечает 409 со списком кандидатов,
 * их предлагаем выбрать), объект, тип изделия, количество, срок, менеджер.
 */
export function NewInquiryDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const templates = useListProductTemplates({ query: { enabled: open, staleTime: 5 * 60_000 } }).data ?? [];
  const employees = useListProductionEmployees({ query: { enabled: open, staleTime: 5 * 60_000 } }).data ?? [];
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [customer, setCustomer] = useState<{ id: string; name: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [newInn, setNewInn] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [objectName, setObjectName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [due, setDue] = useState("");
  const [managerId, setManagerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setMode("existing");
    setSearch("");
    setCustomer(null);
    setNewName("");
    setNewInn("");
    setCandidates([]);
    setObjectName("");
    setTemplateId("");
    setQuantity("1");
    setDue(addWorkingDays(todayIso(), 40));
    setManagerId("");
    setError("");
  }, [open]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  const parties = useListParties(
    { search: debounced || undefined, page_size: 8 },
    { query: { enabled: open && mode === "existing" } },
  );

  async function submit() {
    setError("");
    if (mode === "existing" && !customer) return setError("Выберите заказчика.");
    if (mode === "new" && !newName.trim()) return setError("Укажите наименование нового заказчика.");
    if (!objectName.trim()) return setError("Укажите объект.");
    if (!(Number(quantity) > 0)) return setError("Количество должно быть больше нуля.");
    if (!due) return setError("Укажите срок.");
    const template = templates.find((t) => t.id === templateId);
    const body: InquiryCreateIn = {
      customer_id: mode === "existing" ? customer!.id : null,
      new_customer: mode === "new" ? { short_name: newName.trim(), inn: newInn.trim() } : null,
      object_name: objectName.trim(),
      template_id: templateId || null,
      product_name: template?.name ?? "",
      quantity,
      due_date: due,
      manager_id: managerId || null,
    };
    setBusy(true);
    try {
      const created = await createInquiry(body);
      toast.success(`Заявка ${created.number} создана`);
      await queryClient.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith("/api/v1/sales"),
      });
      onOpenChange(false);
      onCreated(created.id);
    } catch (e) {
      if (e instanceof ApiError && e.code === "duplicates_found" && Array.isArray(e.details)) {
        setCandidates(e.details as Candidate[]);
        toast.warning("Найдены похожие контрагенты", { description: "Выберите существующего или уточните данные." });
      } else {
        toast.error(e instanceof ApiError ? e.message : "Не удалось создать заявку.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" data-testid="new-inquiry-dialog">
        <DialogHeader>
          <DialogTitle>Новая заявка</DialogTitle>
          <DialogDescription>Калькуляцию и план можно заполнить по шаблону изделия в карточке заявки.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex gap-1 rounded-lg bg-muted p-0.5 text-sm">
            {(
              [
                ["existing", "Заказчик из справочника"],
                ["new", "Новый заказчик"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={cn("flex-1 rounded-md px-2 py-1 text-muted-foreground", mode === id && "bg-background font-medium text-foreground shadow-sm")}
                onClick={() => setMode(id)}
              >
                {label}
              </button>
            ))}
          </div>
          {mode === "existing" ? (
            <div className="flex flex-col gap-1.5">
              {customer ? (
                <div className="flex items-center gap-2 text-sm">
                  Заказчик: <b>{customer.name}</b>
                  <Button size="xs" variant="ghost" onClick={() => setCustomer(null)}>
                    изменить
                  </Button>
                </div>
              ) : (
                <>
                  <TextInput placeholder="Поиск по наименованию или ИНН" value={search} name="customer-search" onChange={(e) => setSearch(e.target.value)} />
                  <div className="max-h-40 overflow-auto rounded-md border">
                    {(parties.data?.items ?? []).map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        className="flex w-full justify-between px-2 py-1 text-left text-sm hover:bg-muted"
                        onClick={() => setCustomer({ id: p.id, name: p.short_name })}
                      >
                        <span>{p.short_name}</span>
                        <span className="text-xs text-muted-foreground">{p.inn}</span>
                      </button>
                    ))}
                    {parties.data && !parties.data.items.length ? <div className="px-2 py-1 text-xs text-muted-foreground">Не найдено.</div> : null}
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-[1fr_160px] gap-2">
              <Field label="Краткое наименование">
                <TextInput value={newName} name="new-customer-name" onChange={(e) => setNewName(e.target.value)} />
              </Field>
              <Field label="ИНН">
                <TextInput value={newInn} onChange={(e) => setNewInn(e.target.value)} />
              </Field>
              {candidates.length ? (
                <div className="col-span-2 rounded-md bg-amber-50 p-2 text-sm text-amber-900">
                  Похожие контрагенты:
                  {candidates.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="ml-2 underline"
                      onClick={() => {
                        setMode("existing");
                        setCustomer({ id: c.id, name: c.label });
                      }}
                    >
                      {c.label}
                      {c.inn ? ` (${c.inn})` : ""}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          )}
          <Field label="Объект">
            <TextInput value={objectName} name="object-name" onChange={(e) => setObjectName(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Тип изделия (шаблон)">
              <NativeSelect value={templateId} name="template" onChange={(e) => setTemplateId(e.target.value)}>
                <option value="">—</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.code} — {t.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Количество, шт.">
              <TextInput type="number" min={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            </Field>
            <Field label="Требуемый срок">
              <TextInput type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </Field>
            <Field label="Менеджер проекта">
              <NativeSelect value={managerId} onChange={(e) => setManagerId(e.target.value)}>
                <option value="">— я —</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={submit} disabled={busy}>
            Создать заявку
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
