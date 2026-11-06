"use client";

import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type GatedButtonProps = ComponentProps<typeof Button> & {
  allowed: boolean;
  reason?: string;
};

/**
 * Кнопка действия, гейтованного правом (Правка 2, `docs/spec/10-crm.md` §6, п. 2.1а):
 * вместо исчезновения при `allowed === false` — неактивный элемент с подсказкой,
 * называющей причину. Кнопка, скрытая по правам без объяснения, неотличима от
 * сломанной — восьмой случай класса «элемент интерфейса без механизма», вывернутый
 * наизнанку: механизм есть, элемента нет, никто не сказал почему.
 *
 * `TooltipTrigger` оборачивает `<span>`, а не саму кнопку: у `disabled`-кнопки
 * `pointer-events-none` (`button.tsx`) — она не получает событий мыши, значит
 * не открыла бы подсказку по наведению. `span` вокруг неё получает, `tabIndex`
 * даёт доступ с клавиатуры.
 */
export function GatedButton({
  allowed,
  reason,
  disabled,
  children,
  ...props
}: GatedButtonProps) {
  const button = (
    <Button disabled={disabled || !allowed} {...props}>
      {children}
    </Button>
  );

  if (allowed || !reason) {
    return button;
  }

  return (
    <Tooltip>
      <TooltipTrigger render={<span tabIndex={0} className="inline-flex" />}>
        {button}
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  );
}
