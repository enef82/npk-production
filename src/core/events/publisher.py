"""Публикация доменных событий в outbox. Единственная точка записи в OutboxEvent."""

from __future__ import annotations

from django.db import transaction

from src.core.events.base import DomainEvent
from src.core.events.models import OutboxEvent


class PublishOutsideTransactionError(RuntimeError):
    """`publish()` вызван вне открытой транзакции — нарушен инвариант И4."""


def publish(event: DomainEvent) -> OutboxEvent:
    """Пишет событие в outbox. Обязана вызываться внутри уже открытой `transaction.atomic()`.

    Так событие фиксируется в той же транзакции, что и изменение состояния, и
    откатывается вместе с ней — без этого outbox отражал бы события, которых
    в системе не произошло.
    """

    if not transaction.get_connection().in_atomic_block:
        raise PublishOutsideTransactionError(
            "publish() должен вызываться внутри уже открытой transaction.atomic()"
        )

    return OutboxEvent.objects.create(
        event_type=event.event_type,
        version=event.version,
        aggregate_id=event.aggregate_id,
        payload=event.to_payload(),
    )
