"""Обработка outbox. Единственное место, где меняется состояние OutboxEvent/ProcessedEvent
(инвариант И3 — транзакции открываются только в services/).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from src.core.events import registry
from src.core.events.models import OutboxEvent, ProcessedEvent

logger = logging.getLogger(__name__)


def dispatch_batch(batch_size: int | None = None) -> int:
    batch_size = batch_size if batch_size is not None else settings.EVENTS_DISPATCH_BATCH_SIZE
    now = timezone.now()

    with transaction.atomic():
        event_ids = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(processed_at__isnull=True)
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .exclude(attempts__gte=settings.EVENTS_MAX_ATTEMPTS)
            .order_by("occurred_at")
            .values_list("id", flat=True)[:batch_size]
        )

    for event_id in event_ids:
        _dispatch_one(event_id)

    return len(event_ids)


def _dispatch_one(event_id: int) -> None:
    with transaction.atomic():
        event = (
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(id=event_id, processed_at__isnull=True)
            .first()
        )
        if event is None:
            # Уже обработано или подхвачено другим воркером — пропускаем без ошибки.
            return
        _process(event)


def _process(event: OutboxEvent) -> None:
    handlers = registry.get_handlers(event.event_type)
    succeeded = True

    for handler in handlers:
        name = registry.handler_name(handler)
        if ProcessedEvent.objects.filter(event_id=event.id, handler_name=name).exists():
            continue

        try:
            handler(event)
        except Exception as exc:  # noqa: BLE001 — сбой одного обработчика не должен ронять остальных
            succeeded = False
            record_failure(event, name, exc)
        else:
            ProcessedEvent.objects.create(event_id=event.id, handler_name=name)

    if succeeded:
        mark_processed(event)
    else:
        event.save(update_fields=["attempts", "last_error", "next_attempt_at"])


def mark_processed(event: OutboxEvent) -> None:
    event.processed_at = timezone.now()
    event.next_attempt_at = None
    event.save(update_fields=["processed_at", "next_attempt_at"])


def record_failure(event: OutboxEvent, handler_name: str, error: Exception) -> None:
    event.attempts += 1
    event.last_error = f"{handler_name}: {error}"
    event.next_attempt_at = timezone.now() + _backoff_delay(event.attempts)

    logger.exception(
        "Обработчик %s упал на событии %s (id=%s), попытка %s",
        handler_name,
        event.event_type,
        event.id,
        event.attempts,
    )
    if event.attempts >= settings.EVENTS_MAX_ATTEMPTS:
        logger.critical(
            "Событие %s (id=%s) требует внимания: исчерпан лимит попыток (%s)",
            event.event_type,
            event.id,
            event.attempts,
        )


def _backoff_delay(attempts: int) -> timedelta:
    base = settings.EVENTS_RETRY_BACKOFF_BASE_SECONDS
    cap = settings.EVENTS_RETRY_BACKOFF_MAX_SECONDS
    seconds = min(base * (2 ** (attempts - 1)), cap)
    return timedelta(seconds=seconds)
