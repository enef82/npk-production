"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Kpi, KpiRow } from "@/components/charts/kpi";
import { parseDecimalInput, sumDecimals } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import {
  closeRepair,
  createRepair,
  startRepair,
  updateRepair,
  useGetEquipment,
  useGetEquipmentReference,
  useGetRepair,
  useListEquipment,
  type RepairIn,
  type RepairKind,
  type RepairOut,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { cn } from "@/lib/utils";

import { useInvalidateEquipment, useNames } from "./equipment-view";
import {
  REPAIR_KIND_LABELS,
  REPAIR_STATUS_LABELS,
  REPAIR_STATUS_TONE,
  formatLocal,
  fromLocalInput,
  nowLocalInput,
  num,
  toLocalInput,
} from "./labels";
import { WorkersEditor, type WorkerRow } from "./workers-editor";

export type RepairDraft = { mode: "new"; equipmentId?: string; kind: RepairKind } | { mode: "edit"; id: string };

type Form = {
  equipment_id: string;
  kind: RepairKind;
  started_at: string;
  finished_at: string;
  category_id: string;
  maintenance_type_id: string;
  alarm_code: string;
  description: string;
  fix: string;
  parts: string;
  workers: WorkerRow[];
};

function formOf(r: RepairOut): Form {
  return {
    equipment_id: r.equipment_id,
    kind: r.kind,
    started_at: toLocalInput(r.started_at),
    finished_at: toLocalInput(r.finished_at),
    category_id: r.category_id ?? "",
    maintenance_type_id: r.maintenance_type_id ?? "",
    alarm_code: r.alarm_code,
    description: r.description,
    fix: r.fix,
    parts: r.parts,
    workers: r.workers.map((w) => ({ employee_id: w.employee_id, hours: w.hours })),
  };
}

function payload(f: Form): RepairIn {
  return {
    kind: f.kind,
    started_at: fromLocalInput(f.started_at) ?? "",
    finished_at: fromLocalInput(f.finished_at),
    description: f.description,
    category_id: f.kind !== "maintenance" ? f.category_id || null : null,
    maintenance_type_id: f.kind === "maintenance" ? f.maintenance_type_id || null : null,
    alarm_code: f.kind !== "maintenance" ? f.alarm_code : "",
    fix: f.fix,
    parts: f.parts,
    workers: f.workers.map((w) => ({ employee_id: w.employee_id, hours: parseDecimalInput(w.hours) ?? "0" })),
  };
}

export function RepairDialog({ draft, onClose }: { draft: RepairDraft; onClose: () => void }) {
  const existing = useGetRepair(draft.mode === "edit" ? draft.id : "", { query: { enabled: draft.mode === "edit" } });
  const machines = useListEquipment();
  const ready = draft.mode === "new" ? Boolean(machines.data) : Boolean(existing.data);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl" data-testid="repair-dialog">
        {ready ? (
          <RepairForm
            initial={draft.mode === "edit" ? existing.data! : null}
            initialForm={
              draft.mode === "edit"
                ? formOf(existing.data!)
                : {
                    equipment_id: draft.equipmentId ?? machines.data?.[0]?.id ?? "",
                    kind: draft.kind,
                    started_at: nowLocalInput(),
                    finished_at: "",
                    category_id: "",
                    maintenance_type_id: "",
                    alarm_code: "",
                    description: "",
                    fix: "",
                    parts: "",
                    workers: [],
                  }
            }
            onClose={onClose}
          />
        ) : (
          <DialogHeader>
            <DialogTitle>Авария / ремонт</DialogTitle>
            <DialogDescription>Загрузка…</DialogDescription>
          </DialogHeader>
        )}
      </DialogContent>
    </Dialog>
  );
}

function RepairForm({
  initial,
  initialForm,
  onClose,
}: {
  initial: RepairOut | null;
  initialForm: Form;
  onClose: () => void;
}) {
  const [repair, setRepair] = useState<RepairOut | null>(initial);
  const [form, setForm] = useState<Form>(initialForm);
  const [busy, setBusy] = useState(false);
  const invalidate = useInvalidateEquipment();
  const reference = useGetEquipmentReference();
  const machines = useListEquipment();
  const machine = useGetEquipment(form.equipment_id, { query: { enabled: Boolean(form.equipment_id) } });
  const { workers } = useNames();
  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));

  const editable = repair ? repair.abilities.can_edit : true;
  const operator = workers.find((w) => w.work_center_id && w.work_center_id === machine.data?.work_center_id);
  const labor = sumDecimals(form.workers.map((w) => parseDecimalInput(w.hours) ?? "0"));

  async function act(run: () => Promise<RepairOut>, done: string, close = false) {
    setBusy(true);
    try {
      const result = await run();
      setRepair(result);
      setForm(formOf(result));
      toast.success(done);
      await invalidate();
      if (close) onClose();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось сохранить запись.");
    } finally {
      setBusy(false);
    }
  }

  const field = (label: string, input: React.ReactNode, wide = false) => (
    <label className={cn("flex flex-col gap-1 text-xs text-muted-foreground", wide && "col-span-2")}>
      {label}
      {input}
    </label>
  );

  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-3 pr-8">
          <DialogTitle>
            {repair ? `${repair.number} · ${REPAIR_KIND_LABELS[repair.kind]}` : `Новая запись · ${REPAIR_KIND_LABELS[form.kind]}`}
          </DialogTitle>
          {repair && (
            <span
              className={cn("rounded-full px-2 py-0.5 text-xs font-medium", REPAIR_STATUS_TONE[repair.status])}
              data-testid="repair-status"
            >
              {REPAIR_STATUS_LABELS[repair.status]}
            </span>
          )}
        </div>
        <DialogDescription>
          {repair
            ? `${repair.equipment_inventory_no} · ${repair.equipment_name} · зарегистрирована ${formatLocal(repair.created_at)}`
            : "Авария, плановый ремонт или ТО: простой, исполнители и часы."}
        </DialogDescription>
      </DialogHeader>

      <div className="grid grid-cols-2 gap-3">
        {field(
          "Оборудование",
          <NativeSelect
            aria-label="Оборудование"
            disabled={Boolean(repair)}
            value={form.equipment_id}
            onChange={(e) => set({ equipment_id: e.target.value, maintenance_type_id: "" })}
          >
            {machines.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.inventory_no} · {m.name}
              </option>
            ))}
          </NativeSelect>,
        )}
        {field(
          "Вид",
          <NativeSelect
            aria-label="Вид записи"
            disabled={!editable}
            value={form.kind}
            onChange={(e) => set({ kind: e.target.value as RepairKind })}
          >
            {Object.entries(REPAIR_KIND_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </NativeSelect>,
        )}
        {field(
          "Начало простоя",
          <Input
            type="datetime-local"
            aria-label="Начало простоя"
            disabled={!editable}
            value={form.started_at}
            onChange={(e) => set({ started_at: e.target.value })}
          />,
        )}
        {field(
          "Окончание (оборудование в работе)",
          <Input
            type="datetime-local"
            aria-label="Окончание простоя"
            disabled={!editable}
            value={form.finished_at}
            onChange={(e) => set({ finished_at: e.target.value })}
          />,
        )}
        {form.kind === "maintenance" ? (
          field(
            "Вид ТО",
            <NativeSelect
              aria-label="Вид ТО"
              disabled={!editable}
              value={form.maintenance_type_id}
              onChange={(e) => set({ maintenance_type_id: e.target.value })}
            >
              <option value="">—</option>
              {machine.data?.maintenance.map((t) => (
                <option key={t.maintenance_type_id} value={t.maintenance_type_id}>
                  {t.code} — {t.scope}
                </option>
              ))}
            </NativeSelect>,
            true,
          )
        ) : (
          <>
            {field(
              "Категория отказа",
              <NativeSelect
                aria-label="Категория отказа"
                disabled={!editable}
                value={form.category_id}
                onChange={(e) => set({ category_id: e.target.value })}
              >
                <option value="">—</option>
                {reference.data?.failure_categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>,
            )}
            {field(
              "Код аварии (из SCADA / ЧПУ)",
              <Input
                aria-label="Код аварии"
                disabled={!editable}
                placeholder="E-207"
                value={form.alarm_code}
                onChange={(e) => set({ alarm_code: e.target.value })}
              />,
            )}
          </>
        )}
        {field(
          form.kind === "fail" ? "Что произошло" : "Работы",
          <Textarea
            aria-label="Описание"
            disabled={!editable}
            value={form.description}
            onChange={(e) => set({ description: e.target.value })}
          />,
          true,
        )}
        {field(
          "Что сделано, причина",
          <Input aria-label="Что сделано" disabled={!editable} value={form.fix} onChange={(e) => set({ fix: e.target.value })} />,
          true,
        )}
        {field(
          "Запчасти и материалы",
          <Input
            aria-label="Запчасти"
            disabled={!editable}
            value={form.parts}
            onChange={(e) => set({ parts: e.target.value })}
          />,
          true,
        )}
      </div>

      <h3 className="text-sm font-semibold">Исполнители и трудозатраты</h3>
      <WorkersEditor
        rows={form.workers}
        workers={workers}
        defaultEmployeeId={operator?.employee_id}
        disabled={!editable}
        onChange={(rows) => set({ workers: rows })}
      />

      <KpiRow>
        <Kpi
          value={repair ? `${num(repair.downtime_hours)} ч` : "—"}
          label={repair && !repair.finished_at ? "простой (идёт)" : "простой"}
        />
        <Kpi value={`${num(labor)} чел·ч`} label="трудозатраты" />
        <Kpi value={repair?.status === "done" ? "✓" : "—"} label="в табеле" />
      </KpiRow>
      {repair?.status !== "done" && (
        <p className="text-xs text-muted-foreground">
          При закрытии часы исполнителей переносятся в табель на объект «Ремонт и ТО оборудования».
        </p>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Закрыть окно
        </Button>
        {!repair && (
          <Button
            disabled={busy}
            onClick={() =>
              act(() => createRepair({ equipment_id: form.equipment_id, ...payload(form) }), "Запись зарегистрирована")
            }
          >
            Зарегистрировать
          </Button>
        )}
        {repair?.abilities.can_edit && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => act(() => updateRepair(repair.id, payload(form)), "Запись сохранена")}
          >
            Сохранить
          </Button>
        )}
        {repair?.abilities.can_start && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              act(async () => {
                await updateRepair(repair.id, payload(form));
                return startRepair(repair.id);
              }, `${repair.number}: в ремонте`)
            }
          >
            В ремонт
          </Button>
        )}
        {repair?.abilities.can_close && (
          <Button
            disabled={busy}
            onClick={() =>
              act(
                async () => {
                  await updateRepair(repair.id, payload(form));
                  return closeRepair(repair.id, { finished_at: fromLocalInput(form.finished_at) });
                },
                `${repair.number}: устранено`,
              )
            }
          >
            Устранено — закрыть
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
