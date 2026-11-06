"""Фактическая отправка одного уведомления по каналу «Почта». Вызывается из
`tasks.send_notification_task` (оркестрация — там, логика отправки — здесь)."""

from __future__ import annotations

from uuid import UUID

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from src.core.notifications.models import Notification, NotificationChannel, NotificationStatus


def deliver_notification(notification_id: UUID) -> None:
    with transaction.atomic():
        notification = Notification.objects.select_for_update().get(id=notification_id)
        if notification.status != NotificationStatus.PENDING:
            return

        if notification.channel == NotificationChannel.EMAIL:
            send_mail(
                subject=notification.subject,
                message=notification.body,
                from_email=None,
                recipient_list=[notification.user.email],
                fail_silently=False,
            )

        notification.status = NotificationStatus.SENT
        notification.sent_at = timezone.now()
        notification.save(update_fields=["status", "sent_at", "updated_at"])
