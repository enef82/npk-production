"""Запросы на чтение и агрегаты модуля «Ядро: события»."""

from __future__ import annotations

from django.conf import settings
from django.db.models import QuerySet

from src.core.events.models import OutboxEvent


def iter_stuck_events() -> QuerySet[OutboxEvent]:
    """События, исчерпавшие лимит попыток обработки — диспетчер их больше не выбирает."""

    return OutboxEvent.objects.filter(
        processed_at__isnull=True,
        attempts__gte=settings.EVENTS_MAX_ATTEMPTS,
    ).order_by("occurred_at")
