"""Celery-задачи модуля «Ядро: события»: только оркестрация, логика — в dispatcher.py."""

from __future__ import annotations

from celery import shared_task

from src.core.events import dispatcher


@shared_task(name="core_events.dispatch_pending_events")  # type: ignore[untyped-decorator]
def dispatch_pending_events(batch_size: int | None = None) -> int:
    return dispatcher.dispatch_pending_events(batch_size=batch_size)
