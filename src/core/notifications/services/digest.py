"""Сборка дайджеста — одного сообщения вместо потока однотипных уведомлений.

Периодически вызывается Celery Beat (`tasks.run_notification_digest`), но не зависит от
Celery — вызывается напрямую и в тестах."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.notifications.models import (
    Notification,
    NotificationDeliveryMode,
    NotificationDigest,
    NotificationStatus,
)


def run_notification_digest() -> list[NotificationDigest]:
    pending = (
        Notification.objects.filter(
            delivery_mode=NotificationDeliveryMode.DIGEST,
            status=NotificationStatus.PENDING,
        )
        .values_list("user_id", "channel")
        .distinct()
    )

    return [build_digest_for_user_channel(user_id, channel) for user_id, channel in pending]


def build_digest_for_user_channel(user_id: UUID, channel: str) -> NotificationDigest:
    with transaction.atomic():
        items = list(
            Notification.objects.select_for_update()
            .filter(
                user_id=user_id,
                channel=channel,
                delivery_mode=NotificationDeliveryMode.DIGEST,
                status=NotificationStatus.PENDING,
            )
            .order_by("created_at")
        )
        now = timezone.now()
        period_start = items[0].created_at if items else now

        digest = NotificationDigest.objects.create(
            user_id=user_id,
            channel=channel,
            period_start=period_start,
            period_end=now,
            subject=f"Уведомления ({len(items)})",
            body="\n\n".join(f"{item.subject}\n{item.body}".strip() for item in items),
        )
        digest.items.set(items)

        Notification.objects.filter(id__in=[item.id for item in items]).update(
            status=NotificationStatus.DIGESTED
        )

    return digest
