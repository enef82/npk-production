"""Дайджест — одно собранное сообщение вместо потока однотипных уведомлений за период."""

from django.conf import settings
from django.db import models

from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import NotificationChannel, NotificationStatus
from .notification import Notification


class NotificationDigest(UUIDPrimaryKeyModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_digests",
        verbose_name="Пользователь",
    )
    channel = models.CharField("Канал", max_length=16, choices=NotificationChannel.choices)
    period_start = models.DateTimeField("Начало периода")
    period_end = models.DateTimeField("Конец периода")
    items = models.ManyToManyField(Notification, related_name="digest", verbose_name="Уведомления")
    subject = models.CharField("Тема", max_length=255, blank=True)
    body = models.TextField("Текст")
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )
    sent_at = models.DateTimeField("Отправлено", null=True, blank=True)

    class Meta:
        verbose_name = "Дайджест уведомлений"
        verbose_name_plural = "Дайджесты уведомлений"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Дайджест {self.user_id} за {self.period_start:%Y-%m-%d}"
