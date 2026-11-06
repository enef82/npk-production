"use client";

import { useState } from "react";
import { toast } from "sonner";

import { parseDecimalInput } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { performMaintenance, type EquipmentOut, type MaintenanceStateOut } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";

import { useNames } from "./equipment-view";
import { fromLocalInput, nowLocalInput, num, toLocalInput } from "./labels";
import { WorkersEditor, type WorkerRow } from "./workers-editor";

/** «Провести ТО»: закрытая запись журнала вида «ТО», отметка о проведённом ТО и часы
 * исполнителей в табель. */
export function MaintenanceDialog({
  machine,
  maintenance,
  onClose,
  onDone,
}: {
  machine: EquipmentOut;
  maintenance: MaintenanceStateOut;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const { workers } = useNames();
  const operator = workers.find((w) => w.work_center_id && w.work_center_id === machine.work_center_id);
  const [started, setStarted] = useState(() => toLocalInput(new Date(Date.now() - 4 * 3600_000).toISOString()));
  const [finished, setFinished] = useState(nowLocalInput);
  const [comment, setComment] = useState("");
  const [rows, setRows] = useState<WorkerRow[]>(() =>
    operator ? [{ employee_id: operator.employee_id, hours: "3" }] : [],
  );
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      await performMaintenance(maintenance.maintenance_type_id, {
        started_at: fromLocalInput(started) ?? "",
        finished_at: fromLocalInput(finished) ?? "",
        comment,
        workers: rows.map((r) => ({ employee_id: r.employee_id, hours: parseDecimalInput(r.hours) ?? "0" })),
      });
      toast.success(`${maintenance.code} зарегистрировано`);
      await onDone();
      onClose();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось зарегистрировать ТО.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {maintenance.code}: {machine.name}
          </DialogTitle>
          <DialogDescription>
            {maintenance.scope} · моточасы {num(machine.operating_hours, 0)}
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Начало
            <Input type="datetime-local" value={started} onChange={(e) => setStarted(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Окончание
            <Input type="datetime-local" value={finished} onChange={(e) => setFinished(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Что сделано, замечания
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        <WorkersEditor rows={rows} workers={workers} defaultEmployeeId={operator?.employee_id} onChange={setRows} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button disabled={saving} onClick={submit}>
            Зарегистрировать ТО
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
