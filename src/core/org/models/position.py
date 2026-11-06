"""Должность — справочник без штатного расписания и без ставок."""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import PositionCategory


@track()
class Position(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField("Наименование", max_length=255)
    category = models.CharField("Категория", max_length=16, choices=PositionCategory.choices)
    grade = models.CharField("Разряд", max_length=32, blank=True)

    class Meta:
        verbose_name = "Должность"
        verbose_name_plural = "Должности"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
