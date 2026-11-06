"""Единица измерения."""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class UnitOfMeasure(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=16, unique=True)
    name = models.CharField("Наименование", max_length=64)
    okei_code = models.CharField("Код ОКЕИ", max_length=3, blank=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Единица измерения"
        verbose_name_plural = "Единицы измерения"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code
