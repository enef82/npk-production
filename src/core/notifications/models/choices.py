"""Перечисления модуля «Ядро: уведомления»."""

from django.db import models


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Почта"
    IN_APP = "in_app", "В приложении"


class NotificationDeliveryMode(models.TextChoices):
    IMMEDIATE = "immediate", "Немедленно"
    DIGEST = "digest", "Дайджестом"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Ожидает отправки"
    SENT = "sent", "Отправлено"
    FAILED = "failed", "Ошибка отправки"
    DIGESTED = "digested", "Включено в дайджест"
