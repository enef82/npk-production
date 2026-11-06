"""Настройка уведомлений пользователя: включён ли канал/код и режим доставки. `code=""`
— настройка по умолчанию для канала, когда точечной настройки под конкретный код нет."""

from django.conf import settings
from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import NotificationChannel, NotificationDeliveryMode


@track()
class UserNotificationSetting(UUIDPrimaryKeyModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_settings",
        verbose_name="Пользователь",
    )
    code = models.CharField("Код уведомления", max_length=255, blank=True)
    channel = models.CharField("Канал", max_length=16, choices=NotificationChannel.choices)
    is_enabled = models.BooleanField("Включено", default=True)
    delivery_mode = models.CharField(
        "Режим доставки",
        max_length=16,
        choices=NotificationDeliveryMode.choices,
        default=NotificationDeliveryMode.IMMEDIATE,
    )

    class Meta:
        verbose_name = "Настройка уведомлений пользователя"
        verbose_name_plural = "Настройки уведомлений пользователей"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "code", "channel"],
                name="core_notifications_setting_uniq_user_code_channel",
            ),
        ]
        ordering = ["user", "code", "channel"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.code or '*'}/{self.channel}"
