"use client";

import { useState } from "react";
import { toast } from "sonner";

import { StackChart } from "@/components/charts/stack-chart";
import { parseDecimalInput } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  recordRuntime,
  setEquipmentStatus,
  useGetEquipment,
  useGetEquipmentReference,
  type EquipmentOut,
  type EquipmentStatus,
  type MaintenanceStateOut,
  type ReferenceOut,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { cn } from "@/lib/utils";

import { useInvalidateEquipment, useNames } from "./equipment-view";
import {
  EQUIPMENT_STATUS_LABELS,
  EQUIPMENT_STATUS_TONE,
  MAINTENANCE_TONE,
  REPAIR_KIND_LABELS,
  REPAIR_KIND_TONE,
  REPAIR_STATUS_LABELS,
  REPAIR_STATUS_TONE,
  formatLocal,
  num,
  shortDate,
  todayIso,
} from "./labels";
import { MaintenanceDialog } from "./maintenance-dialog";
import type { RepairDraft } from "./repair-dialog";

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="flex-1" />
        {action}
      </div>
      {children}
    </section>
  );
}

export function MachineSheet({
  machineId,
  onClose,
  onOpenRepair,
}: {
  machineId: string | null;
  onClose: () => void;
  onOpenRepair: (draft: RepairDraft) => void;
}) {
  const query = useGetEquipment(machineId ?? "", { query: { enabled: Boolean(machineId) } });
  return (
    <Sheet open={Boolean(machineId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-5xl data-[side=right]:sm:max-w-5xl">
        {query.data ? (
          <MachineCard machine={query.data} onOpenRepair={onOpenRepair} />
        ) : (
          <SheetHeader>
            <SheetTitle>Оборудование</SheetTitle>
            <SheetDescription>Загрузка…</SheetDescription>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  );
}

function MachineCard({ machine: m, onOpenRepair }: { machine: EquipmentOut; onOpenRepair: (d: RepairDraft) => void }) {
  const names = useNames();
  const invalidate = useInvalidateEquipment();
  const reference = useGetEquipmentReference();
  const [performing, setPerforming] = useState<MaintenanceStateOut | null>(null);
  const center = m.work_center_id ? names.workCenter.get(m.work_center_id) : undefined;
  const a = m.abilities;

  async function changeStatus(status: EquipmentStatus) {
    try {
      await setEquipmentStatus(m.id, { status });
      toast.success(`Состояние: ${EQUIPMENT_STATUS_LABELS[status]}`);
      await invalidate();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось сменить состояние.");
    }
  }

  return (
    <div className="flex flex-col gap-5 p-4" data-testid="machine-card">
      <SheetHeader className="p-0">
        <div className="flex items-center gap-3 pr-8">
          <SheetTitle className="text-base">{m.name}</SheetTitle>
          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", EQUIPMENT_STATUS_TONE[m.status])}>
            {EQUIPMENT_STATUS_LABELS[m.status]}
          </span>
        </div>
        <SheetDescription>
          {m.inventory_no} · {center ? center.name : "общезаводское"} · {m.control_system || "без ЧПУ"} · моточасы{" "}
          <b>{num(m.operating_hours, 0)}</b> · подключение: {m.connection || "—"}
        </SheetDescription>
      </SheetHeader>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-5">
          <Section title="Наработка по неделям, ч">
            <StackChart
              categories={m.weeks.map((w) => shortDate(w.week_start))}
              height={220}
              width={480}
              series={[
                { name: "Работа", color: "#2f5bd3", values: m.weeks.map((w) => Number(w.run)) },
                { name: "Наладка", color: "#9fb4ea", values: m.weeks.map((w) => Number(w.setup)) },
                { name: "Простой", color: "#e9d8a6", values: m.weeks.map((w) => Number(w.idle)) },
                { name: "Отказ", color: "#c53030", values: m.weeks.map((w) => Number(w.down)) },
              ]}
            />
          </Section>

          {a.can_log_runtime && reference.data && (
            <RuntimeForm machineId={m.id} reference={reference.data} onSaved={invalidate} />
          )}

          <Section title="Журнал смен">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 font-medium">Дата</th>
                  <th className="text-right font-medium">Работа</th>
                  <th className="text-right font-medium">Наладка</th>
                  <th className="text-right font-medium">Простой</th>
                  <th className="text-right font-medium">Отказ</th>
                  <th className="pl-3 font-medium">Причина</th>
                  <th className="font-medium">Источник</th>
                </tr>
              </thead>
              <tbody data-testid="runtime-log">
                {m.recent_runtime.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="py-1">{shortDate(r.date)}</td>
                    <td className="text-right tabular-nums">{num(r.run)}</td>
                    <td className="text-right tabular-nums">{num(r.setup)}</td>
                    <td className="text-right tabular-nums">{num(r.idle)}</td>
                    <td className="text-right tabular-nums">{num(r.down)}</td>
                    <td className="pl-3 text-xs text-muted-foreground">
                      {[r.idle_reason_name, r.down_reason_name].filter(Boolean).join(", ")}
                    </td>
                    <td className="text-xs text-muted-foreground">{r.source === "scada" ? "SCADA" : "вручную"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>

        <div className="flex flex-col gap-5">
          <Section title="Техническое обслуживание">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="text-left">
                  <th className="py-1 font-medium">Вид</th>
                  <th className="text-right font-medium">Интервал</th>
                  <th className="pl-3 font-medium">Последнее</th>
                  <th className="font-medium">Следующее</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {m.maintenance.map((t) => (
                  <tr key={t.maintenance_type_id} className="border-t align-top">
                    <td className="py-1">
                      <b>{t.code}</b>
                      <div className="text-xs text-muted-foreground">{t.scope}</div>
                    </td>
                    <td className="text-right tabular-nums">{num(t.interval_hours, 0)} ч</td>
                    <td className="pl-3 text-xs text-muted-foreground">
                      {t.last_date ? `${shortDate(t.last_date)} · ${num(t.last_at_hours, 0)} ч` : "—"}
                    </td>
                    <td className="text-xs">
                      <span className={cn("rounded px-1.5 py-0.5", MAINTENANCE_TONE[t.state])}>
                        {Number(t.hours_left) <= 0 ? "просрочено" : `через ${num(t.hours_left, 0)} ч`}
                      </span>
                      <div className="text-muted-foreground">≈ {shortDate(t.due_date)}</div>
                    </td>
                    <td className="text-right">
                      {a.can_log_runtime && (
                        <Button size="xs" variant="outline" onClick={() => setPerforming(t)}>
                          Провести ТО
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {a.can_set_status && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Состояние</span>
                <NativeSelect
                  aria-label="Состояние оборудования"
                  className="w-44"
                  value={m.status}
                  onChange={(e) => changeStatus(e.target.value as EquipmentStatus)}
                >
                  {Object.entries(EQUIPMENT_STATUS_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
          </Section>

          <Section
            title="Аварии и ремонты"
            action={
              a.can_register_repair && (
                <div className="flex gap-2">
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => onOpenRepair({ mode: "new", equipmentId: m.id, kind: "fail" })}
                  >
                    Зарегистрировать отказ
                  </Button>
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => onOpenRepair({ mode: "new", equipmentId: m.id, kind: "repair" })}
                  >
                    + ремонт
                  </Button>
                </div>
              )
            }
          >
            {m.recent_repairs.length === 0 ? (
              <p className="text-sm text-muted-foreground">Записей нет.</p>
            ) : (
              <table className="w-full text-sm">
                <tbody>
                  {m.recent_repairs.map((r) => (
                    <tr
                      key={r.id}
                      className="cursor-pointer border-t hover:bg-muted/40"
                      onClick={() => onOpenRepair({ mode: "edit", id: r.id })}
                    >
                      <td className="py-1 text-xs text-muted-foreground">{r.number}</td>
                      <td>
                        <span className={cn("rounded px-1.5 py-0.5 text-xs", REPAIR_KIND_TONE[r.kind])}>
                          {REPAIR_KIND_LABELS[r.kind]}
                        </span>
                      </td>
                      <td className="text-xs">{formatLocal(r.started_at)}</td>
                      <td className="text-right tabular-nums">{num(r.downtime_hours)} ч</td>
                      <td className="text-right tabular-nums">{num(r.labor_hours)} чел·ч</td>
                      <td className="pl-2">
                        <span className={cn("rounded px-1.5 py-0.5 text-xs", REPAIR_STATUS_TONE[r.status])}>
                          {REPAIR_STATUS_LABELS[r.status]}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>
        </div>
      </div>

      {performing && (
        <MaintenanceDialog
          machine={m}
          maintenance={performing}
          onClose={() => setPerforming(null)}
          onDone={invalidate}
        />
      )}
    </div>
  );
}

function RuntimeForm({
  machineId,
  reference,
  onSaved,
}: {
  machineId: string;
  reference: ReferenceOut;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState({
    date: todayIso(),
    run: "6",
    setup: "0.5",
    idle: "1.5",
    idle_reason_id: reference.idle_reasons[0]?.id ?? "",
    down: "0",
    down_reason_id: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const dec = (v: string) => parseDecimalInput(v) ?? "0";

  async function submit() {
    setSaving(true);
    try {
      const idle = dec(form.idle);
      const down = dec(form.down);
      await recordRuntime(machineId, {
        date: form.date,
        run: dec(form.run),
        setup: dec(form.setup),
        idle,
        down,
        idle_reason_id: idle !== "0" ? form.idle_reason_id || null : null,
        down_reason_id: down !== "0" ? form.down_reason_id || null : null,
      });
      toast.success("Смена записана");
      await onSaved();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось записать смену.");
    } finally {
      setSaving(false);
    }
  }

  const field = (label: string, input: React.ReactNode) => (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      {input}
    </label>
  );

  return (
    <Section title="Внести наработку за смену">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {field("Дата", <Input type="date" value={form.date} max={todayIso()} onChange={(e) => set({ date: e.target.value })} />)}
        {field("Работа, ч", <Input inputMode="decimal" value={form.run} onChange={(e) => set({ run: e.target.value })} />)}
        {field("Наладка, ч", <Input inputMode="decimal" value={form.setup} onChange={(e) => set({ setup: e.target.value })} />)}
        {field("Простой, ч", <Input inputMode="decimal" value={form.idle} onChange={(e) => set({ idle: e.target.value })} />)}
        {field(
          "Причина простоя",
          <NativeSelect value={form.idle_reason_id} onChange={(e) => set({ idle_reason_id: e.target.value })}>
            {reference.idle_reasons.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </NativeSelect>,
        )}
        {field("Отказ, ч", <Input inputMode="decimal" value={form.down} onChange={(e) => set({ down: e.target.value })} />)}
        {field(
          "Причина отказа",
          <NativeSelect value={form.down_reason_id} onChange={(e) => set({ down_reason_id: e.target.value })}>
            <option value="">—</option>
            {reference.down_reasons.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </NativeSelect>,
        )}
        <div className="flex items-end">
          <Button className="w-full" disabled={saving} onClick={submit}>
            Записать смену
          </Button>
        </div>
      </div>
    </Section>
  );
}
