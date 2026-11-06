"""ЦФО — отдельная сущность с необязательной ссылкой на подразделение. Без иерархии."""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class CostCenter(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField("Наименование", max_length=255)
    code = models.CharField("Код", max_length=32, unique=True)
    department = models.ForeignKey(
        "core_org.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_centers",
        verbose_name="Подразделение",
    )

    class Meta:
        verbose_name = "ЦФО"
        verbose_name_plural = "ЦФО"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
