"use client";

import { Bell } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/**
 * Пустое состояние: у core.notifications нет API в этом шаге (вне одобренного
 * списка эндпоинтов), поэтому колокольчик не притворяется рабочим — честно
 * показывает «пока нечего показать», а не выдуманные уведомления.
 */
export function NotificationsMenu() {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Уведомления">
            <Bell className="size-4" aria-hidden />
          </Button>
        }
      />
      <PopoverContent align="end" className="w-72 text-sm text-muted-foreground">
        Уведомления появятся на следующих шагах.
      </PopoverContent>
    </Popover>
  );
}
