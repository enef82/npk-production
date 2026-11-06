"""Показывает события outbox, исчерпавшие лимит попыток обработки."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from src.core.events.selectors import iter_stuck_events


class Command(BaseCommand):
    help = "Показывает застрявшие события outbox (исчерпан лимит попыток обработки)."

    def handle(self, *args: Any, **options: Any) -> None:
        события = list(iter_stuck_events())

        if not события:
            self.stdout.write("Застрявших событий нет.")
            return

        for событие in события:
            self.stdout.write(
                f"#{событие.id}\t{событие.event_type}\t"
                f"aggregate_id={событие.aggregate_id}\t"
                f"попыток={событие.attempts}\t"
                f"наступило={событие.occurred_at.isoformat()}\t"
                f"ошибка={событие.last_error!r}"
            )
