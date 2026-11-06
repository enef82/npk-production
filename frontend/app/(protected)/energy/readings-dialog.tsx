"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { parseDecimalInput } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { recordMeterReading, useListMeterReadings, useListMeters } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { formatDateTime } from "@/lib/format/ru";

import { nowHalfHourLocal } from "./dates";

/** Ручной ввод показаний для точек учёта без связи со SCADA: расход между показаниями
 * сервер раскладывает по получасовым интервалам. */
export function ReadingsDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const meters = useListMeters();
  const manual = (meters.data ?? []).filter((m) => m.source === "manual");
  const [chosen, setChosen] = useState("");
  const meterId = chosen || manual[0]?.id || "";
  const meter = manual.find((m) => m.id === meterId);
  const readings = useListMeterReadings(meterId, { query: { enabled: Boolean(meterId) } });
  const [takenAt, setTakenAt] = useState(nowHalfHourLocal);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    const parsed = parseDecimalInput(value);
    if (parsed === null) {
      toast.error("Введите показание числом.");
      return;
    }
    setSaving(true);
    try {
      await recordMeterReading(meterId, { taken_at: new Date(takenAt).toISOString(), value: parsed });
      toast.success(`Показание сохранено: ${meter?.code ?? ""}`);
      setValue("");
      await queryClient.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/api/v1/energy"),
      });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Показание не принято.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Ручной ввод показаний</DialogTitle>
          <DialogDescription>
            Для точек учёта без связи со SCADA. Показание накопительное; время — кратно 30 минутам.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <label className="col-span-2 flex flex-col gap-1 text-xs text-muted-foreground">
            Счётчик
            <NativeSelect aria-label="Счётчик" value={meterId} onChange={(e) => setChosen(e.target.value)}>
              {manual.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.code} · {m.name} ({m.unit})
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Время показания
            <Input
              type="datetime-local"
              step={1800}
              aria-label="Время показания"
              value={takenAt}
              onChange={(e) => setTakenAt(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Показание, {meter?.unit ?? ""}
            <Input aria-label="Показание" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
          </label>
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold">Последние показания</h3>
          {readings.data && readings.data.length > 0 ? (
            <table className="w-full text-sm">
              <tbody>
                {readings.data.slice(0, 8).map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="py-1">{formatDateTime(r.taken_at)}</td>
                    <td className="text-right tabular-nums">{Number(r.value).toLocaleString("ru-RU")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">Показаний ещё нет.</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Закрыть
          </Button>
          <Button disabled={saving || !meterId || !value} onClick={submit}>
            Сохранить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
