"""Перечисления модуля «Ядро: нумерация»."""

from django.db import models


class NumeratorResetPeriod(models.TextChoices):
    NEVER = "never", "Никогда"
    YEARLY = "yearly", "Ежегодно"
    MONTHLY = "monthly", "Ежемесячно"
