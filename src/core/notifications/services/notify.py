"""Постановка уведомлений в очередь. Единственная точка входа для остальных модулей —
`core.notifications.facade.notify()` вызывает эту функцию."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db import transaction
from django.template import Context, Template
from django.utils import timezone

from src.core.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryMode,
    NotificationStatus,
    NotificationTemplate,
    UserNotificationSetting,
)


def _delivery_mode(user_id: UUID, code: str, channel: str) -> tuple[bool, str]:
    """Настройка конкретного кода имеет приоритет над настройкой по умолчанию (`code=""`)
    для этого пользователя и канала. Если настройки вообще нет — включено, немедленно."""

    specific = UserNotificationSetting.objects.filter(
        user_id=user_id, code=code, channel=channel
    ).first()
    if specific is not None:
        return specific.is_enabled, specific.delivery_mode

    default = UserNotificationSetting.objects.filter(
        user_id=user_id, code="", channel=channel
    ).first()
    if default is not None:
        return default.is_enabled, default.delivery_mode

    return True, NotificationDeliveryMode.IMMEDIATE


def notify(user_ids: Iterable[UUID], code: str, context: dict[str, Any]) -> list[Notification]:
    created: list[Notification] = []

    with transaction.atomic():
        templates = list(NotificationTemplate.objects.filter(code=code))
        for user_id in user_ids:
            for template in templates:
                is_enabled, delivery_mode = _delivery_mode(user_id, code, template.channel)
                if not is_enabled:
                    continue

                notification = Notification.objects.create(
                    user_id=user_id,
                    code=code,
                    channel=template.channel,
                    delivery_mode=delivery_mode,
                    subject=Template(template.subject_template).render(Context(context)),
                    body=Template(template.body_template).render(Context(context)),
                    context=context,
                )
                created.append(notification)

                if delivery_mode != NotificationDeliveryMode.IMMEDIATE:
                    continue

                if template.channel == NotificationChannel.EMAIL:
                    _enqueue_send(notification.id)
                else:
                    # «В приложении» не требует отдельной отправки — уведомление уже
                    # видно через выборку по Notification, статус проставляется сразу.
                    notification.status = NotificationStatus.SENT
                    notification.sent_at = timezone.now()
                    notification.save(update_fields=["status", "sent_at", "updated_at"])

    return created


def _enqueue_send(notification_id: UUID) -> None:
    def _send() -> None:
        from src.core.notifications.tasks import send_notification_task

        send_notification_task.delay(str(notification_id))

    transaction.on_commit(_send)
