"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  launchInquiry,
  loseInquiry,
  useListLossReasons,
  usePreviewInquiryLaunch,
  type InquiryCardOut,
} from "@/lib/api/endpoints";
import { addWorkingDays, fdl, nextWorkingDay, todayIso } from "@/lib/production/dates";
import { useAction } from "@/lib/production/use-action";

import { Field, NativeSelect, Note, TextArea, TextInput } from "./bits";

/** Диалог с полем текста: виза с комментарием, причина возврата, комментарий в журнал. */
export function TextDialog({
  open,
  title,
  description,
  label,
  placeholder,
  required,
  okText,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  label: string;
  placeholder?: string;
  required?: boolean;
  okText: string;
  onOpenChange: (open: boolean) => void;
  onSubmit: (text: string) => Promise<unknown> | void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setText("");
      setError("");
    }
  }, [open]);

  async function submit() {
    if (required && !text.trim()) {
      setError("Поле обязательно.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(text.trim());
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription render={<div />}>{description}</DialogDescription> : null}
        </DialogHeader>
        <Field label={label}>
          <TextArea
            autoFocus
            value={text}
            placeholder={placeholder}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={!!error}
          />
        </Field>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={submit} disabled={busy}>
            {okText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Сообщение без действия: «нужна виза ответственного». */
export function InfoDialog({
  open,
  title,
  children,
  onOpenChange,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="text-sm">{children}</div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Закрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * «Запуск в работу» (`launchDialog` прототипа): дата запуска, срок по договору,
 * расчётное окончание и критический путь — с сервера (`launch-preview`), без
 * сохранения, пересчитываются при смене дат.
 */
export function LaunchDialog({
  inquiry,
  open,
  onOpenChange,
  onLaunched,
}: {
  inquiry: InquiryCardOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLaunched?: (orderId: string) => void;
}) {
  const { run, pending } = useAction();
  const [start, setStart] = useState("");
  const [due, setDue] = useState("");

  useEffect(() => {
    if (open && inquiry) {
      const tomorrow = addWorkingDays(todayIso(), 1);
      const planned = inquiry.planned_start && inquiry.planned_start >= todayIso() ? inquiry.planned_start : tomorrow;
      setStart(nextWorkingDay(planned));
      setDue(inquiry.due_date);
    }
  }, [open, inquiry]);

  const preview = usePreviewInquiryLaunch(
    inquiry?.id ?? "",
    { planned_start: start, due_date: due },
    { query: { enabled: open && !!inquiry && !!start && !!due } },
  );
  const p = preview.data;

  async function submit() {
    if (!inquiry || !start || !due) return;
    const result = await run(
      () => launchInquiry(inquiry.id, { planned_start: start, due_date: due }),
      (r) => (r.warnings.length ? undefined : "Производственный заказ создан"),
    );
    if (result) {
      for (const w of result.warnings) toastWarning(w);
      onOpenChange(false);
      onLaunched?.(result.order_id);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Запуск в работу</DialogTitle>
          <DialogDescription>
            По заявке <b>{inquiry?.number}</b> будет создан производственный заказ. Операции калькуляции со связями
            становятся планом выполнения.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Дата запуска">
            <TextInput type="date" name="launch-start" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="Срок по договору">
            <TextInput type="date" name="launch-due" value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
        </div>
        <div className="text-xs text-muted-foreground" data-testid="launch-preview">
          {preview.isFetching && !p ? (
            "Расчёт плана…"
          ) : p && p.planned_finish ? (
            <>
              Плановое окончание: <b className="text-foreground">{fdl(p.planned_finish)}</b> ({p.length} раб. дн.)
              {p.days_late > 0 ? (
                <span className="text-red-600"> — позже срока на {p.days_late} раб. дн.</span>
              ) : (
                <span> — запас {-p.days_late} раб. дн.</span>
              )}
              <br />
              Критический путь: {p.critical_path.join(" → ") || "—"}
            </>
          ) : p ? (
            <Note tone="warn">В калькуляции нет операций — запускать нечего.</Note>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={submit} disabled={pending || !start || !due}>
            Создать заказ
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function toastWarning(message: string) {
  // Предупреждение запуска (нет КД) не блокирует, но должно быть заметнее тоста успеха.
  toast.warning("Заказ создан с предупреждением", { description: message, duration: 8000 });
}

/** Проигрыш заявки — причина из справочника `LossReason` (§7, п. 1). */
export function LoseDialog({
  inquiry,
  open,
  onOpenChange,
}: {
  inquiry: InquiryCardOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { run, pending } = useAction();
  const reasons = useListLossReasons({ query: { enabled: open } });
  const [reasonId, setReasonId] = useState("");
  const [comment, setComment] = useState("");

  useEffect(() => {
    if (open) {
      setReasonId("");
      setComment("");
    }
  }, [open]);

  async function submit() {
    if (!inquiry || !reasonId) return;
    const ok = await run(() => loseInquiry(inquiry.id, { reason_id: reasonId, comment }), `${inquiry.number}: заявка проиграна`);
    if (ok) onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Заявка проиграна</DialogTitle>
          <DialogDescription>
            {inquiry?.number} · {inquiry?.customer_name}. Заявка уйдёт с доски.
          </DialogDescription>
        </DialogHeader>
        <Field label="Причина">
          <NativeSelect value={reasonId} onChange={(e) => setReasonId(e.target.value)} name="loss-reason">
            <option value="">— выберите —</option>
            {(reasons.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Комментарий">
          <TextArea value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button variant="destructive" onClick={submit} disabled={pending || !reasonId}>
            Отметить проигрыш
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
