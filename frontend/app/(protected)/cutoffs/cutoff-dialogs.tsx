"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import type { AnalyticsCutoffWeekOut, AnalyticsWorkedHoursIn } from "@/lib/api/endpoints";
import { weekLabel } from "@/lib/analytics/format";
import { hours, num } from "@/lib/production/format";

/**
 * Закрытие отсечки (`cutBtn` прототипа): отработанные часы подставлены из табеля и
 * правятся до закрытия; после закрытия цифры недели не меняются.
 */
export function CloseCutoffDialog({
  week,
  onClose,
  onConfirm,
}: {
  week: AnalyticsCutoffWeekOut | null;
  onClose: () => void;
  onConfirm: (comment: string, worked: AnalyticsWorkedHoursIn[]) => Promise<void>;
}) {
  return (
    <Dialog open={week !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        {week && <CloseForm key={week.week_start} week={week} onClose={onClose} onConfirm={onConfirm} />}
      </DialogContent>
    </Dialog>
  );
}

function CloseForm({
  week,
  onClose,
  onConfirm,
}: {
  week: AnalyticsCutoffWeekOut;
  onClose: () => void;
  onConfirm: (comment: string, worked: AnalyticsWorkedHoursIn[]) => Promise<void>;
}) {
  const [worked, setWorked] = useState<Record<string, string>>(() =>
    Object.fromEntries(week.rows.map((r) => [r.work_center_id!, String(Math.round(num(r.worked)))])),
  );
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const invalid = Object.values(worked).some((v) => v === "" || Number(v) < 0 || Number.isNaN(Number(v)));

  return (
    <>
      <DialogHeader>
        <DialogTitle>Отсечка недели {weekLabel(week.week_start)}</DialogTitle>
        <DialogDescription>
          Отработанные часы подставлены из табеля (разноска сотрудников участка за неделю). После закрытия данные
          недели фиксируются.
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[50vh] overflow-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Участок</TableHead>
              <TableHead className="text-right">Освоено, н-ч</TableHead>
              <TableHead className="w-32 text-right">Отработано, ч</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {week.rows.map((r) => (
              <TableRow key={r.work_center_id}>
                <TableCell>{r.name}</TableCell>
                <TableCell className="text-right tabular-nums">{hours(r.earned)}</TableCell>
                <TableCell>
                  <Input
                    aria-label={`Отработано: ${r.name}`}
                    className="h-7 text-right"
                    type="number"
                    min="0"
                    step="1"
                    value={worked[r.work_center_id!]}
                    onChange={(e) => setWorked((w) => ({ ...w, [r.work_center_id!]: e.target.value }))}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="cutoff-comment">Комментарий</Label>
        <Input
          id="cutoff-comment"
          placeholder="Например: простой лазера 6 ч, ждали лист"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Отмена
        </Button>
        <Button
          disabled={pending || invalid}
          onClick={async () => {
            setPending(true);
            try {
              await onConfirm(
                comment.trim(),
                Object.entries(worked).map(([work_center_id, h]) => ({ work_center_id, hours: h })),
              );
            } catch {
              // Ошибку показал общий обработчик мутаций — окно остаётся открытым.
            } finally {
              setPending(false);
            }
          }}
        >
          Закрыть отсечку
        </Button>
      </DialogFooter>
    </>
  );
}

/** Переоткрытие: снимок удаляется, причина остаётся в журнале отсечек. */
export function ReopenCutoffDialog({
  week,
  onClose,
  onConfirm,
}: {
  week: string | null;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  return (
    <Dialog
      open={week !== null}
      onOpenChange={(next) => {
        if (!next) {
          setReason("");
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Переоткрыть отсечку {week ? weekLabel(week) : ""}</DialogTitle>
          <DialogDescription>
            Снимок недели будет удалён, неделя снова покажет текущие данные. Причина сохранится в журнале.
          </DialogDescription>
        </DialogHeader>
        <Textarea aria-label="Причина" placeholder="Причина" value={reason} onChange={(e) => setReason(e.target.value)} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Отмена
          </Button>
          <Button
            disabled={!reason.trim() || pending}
            onClick={async () => {
              setPending(true);
              try {
                await onConfirm(reason.trim());
                setReason("");
              } catch {
                // Ошибку показал общий обработчик мутаций — окно остаётся открытым.
              } finally {
                setPending(false);
              }
            }}
          >
            Переоткрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
