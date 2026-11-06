"""Номенклатура — ядро идентичности. Ровно шесть полей, не расширять."""

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import ItemStatus, ItemType
from .uom import UnitOfMeasure


@track()
class Item(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=64, unique=True)
    name = models.CharField("Наименование", max_length=512)
    item_type = models.CharField("Тип номенклатуры", max_length=16, choices=ItemType.choices)
    base_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        verbose_name="Базовая единица измерения",
        related_name="items",
    )
    status = models.CharField(
        "Статус", max_length=16, choices=ItemStatus.choices, default=ItemStatus.DRAFT
    )

    class Meta:
        verbose_name = "Позиция номенклатуры"
        verbose_name_plural = "Номенклатура"
        indexes = [
            GinIndex(
                fields=["name"],
                opclasses=["gin_trgm_ops"],
                name="core_identity_item_name_trgm",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"
