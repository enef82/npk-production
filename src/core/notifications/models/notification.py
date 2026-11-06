"""Уведомление, отправленное конкретному пользователю. `delivery_mode` — снимок настройки
на момент создания (последующая правка настройки не должна задним числом менять уже
поставленные в очередь уведомления)."""

from django.conf import settings
from django.db import models

from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import NotificationChannel, NotificationDeliveryMode, NotificationStatus


class Notification(UUIDPrimaryKeyModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Пользователь",
    )
    code = models.CharField("Код уведомления", max_length=255)
    channel = models.CharField("Канал", max_length=16, choices=NotificationChannel.choices)
    delivery_mode = models.CharField(
        "Режим доставки", max_length=16, choices=NotificationDeliveryMode.choices
    )
    subject = models.CharField("Тема", max_length=255, blank=True)
    body = models.TextField("Текст")
    context = models.JSONField("Контекст", default=dict, blank=True)
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )
    read_at = models.DateTimeField("Прочитано", null=True, blank=True)
    sent_at = models.DateTimeField("Отправлено", null=True, blank=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "channel", "delivery_mode", "status"],
                name="core_notif_pending_by_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} → {self.user_id}"
