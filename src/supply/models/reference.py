"""Справочники снабжения: поставщики и типовая оснастка участков
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4).

`Supplier` — пока имя; профилем поверх `Party` ядра станет при переезде в ИС
(спецификация §3.4). `ToolTemplate.work_center_id` — UUID участка `production` (И2).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import LineCategory


@track()
class Supplier(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField("Наименование", max_length=255, unique=True)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"
        ordering = ["name"]
        permissions = [
            ("order_lines", "Заказ позиций у поставщиков (снабжение)"),
            ("store_lines", "Приёмка, резерв и выдача позиций в производство (склад)"),
        ]

    def __str__(self) -> str:
        return self.name


@track()
class ToolTemplate(UUIDPrimaryKeyModel, TimeStampedModel):
    """Типовая оснастка, инструмент и расходники участка (`TOOL_TPL` прототипа) —
    из неё по маршруту заказа собирается потребность вида «оснастка»."""

    work_center_id = models.UUIDField("Участок")
    category = models.CharField(
        "Категория",
        max_length=16,
        choices=[(c.value, c.label) for c in LineCategory if c != LineCategory.MATERIAL],
    )
    name = models.CharField("Наименование", max_length=255)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=3)
    unit = models.CharField("Ед. изм.", max_length=16)
    price = MoneyField(verbose_name="Цена", default=Decimal("0"))
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Типовая оснастка участка"
        verbose_name_plural = "Типовая оснастка участков"
        ordering = ["work_center_id", "order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_center_id", "name"],
                name="supply_tool_template_unique_name",
                violation_error_message="Такая позиция у участка уже есть.",
            ),
            models.CheckConstraint(
                name="supply_tool_template_quantity_positive",
                condition=Q(quantity__gt=0, price__gte=0),
                violation_error_message="Количество больше нуля, цена не отрицательная.",
            ),
            models.CheckConstraint(
                name="supply_tool_template_not_material",
                condition=~Q(category=LineCategory.MATERIAL),
                violation_error_message="Материалы берутся из калькуляции, не из оснастки.",
            ),
        ]

    def __str__(self) -> str:
        return self.name
