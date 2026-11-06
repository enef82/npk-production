"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { addProductionComment } from "@/lib/api/endpoints";
import { useAction } from "@/lib/production/use-action";

import { TextDialog } from "./stage-dialogs";

/** Комментарий в журнал заказа — к заказу в целом или к операции. */
export function CommentButton({
  orderId,
  operationId,
  label = "Комментарий",
  title,
}: {
  orderId: string;
  operationId?: string;
  label?: React.ReactNode;
  title?: string;
}) {
  const { run } = useAction();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="xs" variant="outline" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <TextDialog
        open={open}
        title={title ?? "Комментарий в журнал"}
        label="Текст"
        required
        okText="Добавить в журнал"
        onOpenChange={setOpen}
        onSubmit={(text) =>
          run(() => addProductionComment(orderId, { text, operation_id: operationId ?? null }), "Запись добавлена в журнал")
        }
      />
    </>
  );
}
