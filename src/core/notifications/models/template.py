"""Шаблон уведомления. `code` совпадает с ключом, которым модули вызывают
`core.notifications.facade.notify()` (часто — с `event_type` события-источника, но не
обязательно: уведомление можно отправить и без события)."""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import NotificationChannel


@track()
class NotificationTemplate(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=255)
    channel = models.CharField("Канал", max_length=16, choices=NotificationChannel.choices)
    subject_template = models.CharField(
        "Шаблон темы", max_length=255, blank=True, help_text="Только для канала «Почта»"
    )
    body_template = models.TextField("Шаблон текста")

    class Meta:
        verbose_name = "Шаблон уведомления"
        verbose_name_plural = "Шаблоны уведомлений"
        constraints = [
            models.UniqueConstraint(
                fields=["code", "channel"],
                name="core_notifications_template_uniq_code_channel",
            ),
        ]
        ordering = ["code", "channel"]

    def __str__(self) -> str:
        return f"{self.code} ({self.get_channel_display()})"
