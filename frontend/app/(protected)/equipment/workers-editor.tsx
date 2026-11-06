"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { TimesheetWorkerOut } from "@/lib/api/endpoints";

export type WorkerRow = { employee_id: string; hours: string };

/** Исполнители и часы: часы при закрытии уходят в табель событием `equipment.repair_closed`. */
export function WorkersEditor({
  rows,
  workers,
  defaultEmployeeId,
  disabled,
  onChange,
}: {
  rows: WorkerRow[];
  workers: TimesheetWorkerOut[];
  defaultEmployeeId?: string;
  disabled?: boolean;
  onChange: (rows: WorkerRow[]) => void;
}) {
  const set = (i: number, patch: Partial<WorkerRow>) => onChange(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  return (
    <div className="flex flex-col gap-2">
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr className="text-left">
            <th className="py-1 font-medium">Сотрудник</th>
            <th className="w-28 text-right font-medium">Часы</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} data-testid="worker-row">
              <td className="py-1 pr-2">
                <NativeSelect
                  aria-label="Исполнитель"
                  disabled={disabled}
                  value={row.employee_id}
                  onChange={(e) => set(i, { employee_id: e.target.value })}
                >
                  {workers.map((w) => (
                    <option key={w.employee_id} value={w.employee_id}>
                      {w.full_name} · {w.department_name}
                    </option>
                  ))}
                </NativeSelect>
              </td>
              <td className="py-1">
                <Input
                  aria-label="Часы исполнителя"
                  inputMode="decimal"
                  className="text-right"
                  disabled={disabled}
                  value={row.hours}
                  onChange={(e) => set(i, { hours: e.target.value })}
                />
              </td>
              <td className="py-1 pl-1">
                {!disabled && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Удалить исполнителя"
                    onClick={() => onChange(rows.filter((_, k) => k !== i))}
                  >
                    <X />
                  </Button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="py-1 text-xs text-muted-foreground" colSpan={3}>
                Исполнители не указаны.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {!disabled && (
        <Button
          variant="outline"
          size="sm"
          className="w-fit"
          disabled={workers.length === 0}
          onClick={() =>
            onChange([...rows, { employee_id: defaultEmployeeId ?? workers[0]?.employee_id ?? "", hours: "1" }])
          }
        >
          + исполнитель
        </Button>
      )}
    </div>
  );
}
