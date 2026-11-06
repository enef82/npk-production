"""Калькуляция заявки: материалы, операции, связи (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.2, «Калькуляция»).

`work_center_id` — UUID участка `production` без внешнего ключа (И2): ставку и признак
снабжения калькуляция читает через `production.facade.list_work_centers`. Что обе
операции связи — одной заявки, проверяет триггер миграции
`0002_calc_dependency_same_inquiry`; отсутствие циклов — сервис.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .inquiry import Inquiry


@track()
class CalcMaterial(UUIDPrimaryKeyModel, TimeStampedModel):
    inquiry = models.ForeignKey(
        Inquiry, on_delete=models.CASCADE, related_name="materials", verbose_name="Заявка"
    )
    name = models.CharField("Наименование", max_length=255)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=3)
    price = MoneyField(verbose_name="Цена")
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Материал калькуляции"
        verbose_name_plural = "Материалы калькуляции"
        ordering = ["inquiry", "sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                name="sales_calc_material_non_negative",
                condition=Q(quantity__gte=0, price__gte=0),
                violation_error_message="Количество и цена не могут быть отрицательными.",
            ),
        ]

    def __str__(self) -> str:
        return self.name


@track()
class CalcOperation(UUIDPrimaryKeyModel, TimeStampedModel):
    inquiry = models.ForeignKey(
        Inquiry, on_delete=models.CASCADE, related_name="operations", verbose_name="Заявка"
    )
    seq = models.PositiveSmallIntegerField("Номер")
    name = models.CharField("Наименование", max_length=255)
    work_center_id = models.UUIDField("Участок")
    hours = models.DecimalField(
        "Трудоёмкость, н-ч (снабжение — дни)", max_digits=10, decimal_places=2
    )
    people = models.PositiveSmallIntegerField("Исполнителей", default=1)
    not_before = models.DateField("Не ранее", null=True, blank=True)
    planned_start = models.DateField("Плановое начало", null=True, blank=True)

    class Meta:
        verbose_name = "Операция калькуляции"
        verbose_name_plural = "Операции калькуляции"
        ordering = ["inquiry", "seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["inquiry", "seq"],
                name="sales_calc_operation_unique_seq",
                violation_error_message="Операция с таким номером в калькуляции уже есть.",
            ),
            models.CheckConstraint(
                name="sales_calc_operation_hours_non_negative",
                condition=Q(hours__gte=0),
                violation_error_message="Трудоёмкость не может быть отрицательной.",
            ),
            models.CheckConstraint(
                name="sales_calc_operation_people",
                condition=Q(people__gte=1),
                violation_error_message="Исполнителей — не меньше одного.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.seq} {self.name}"


@track()
class CalcOperationDependency(UUIDPrimaryKeyModel, TimeStampedModel):
    predecessor = models.ForeignKey(
        CalcOperation,
        on_delete=models.CASCADE,
        related_name="successor_links",
        verbose_name="Предшественник",
    )
    successor = models.ForeignKey(
        CalcOperation,
        on_delete=models.CASCADE,
        related_name="predecessor_links",
        verbose_name="Последователь",
    )

    class Meta:
        verbose_name = "Связь операций калькуляции"
        verbose_name_plural = "Связи операций калькуляции"
        constraints = [
            models.CheckConstraint(
                name="sales_calc_dependency_not_self",
                condition=~Q(predecessor=models.F("successor")),
                violation_error_message="Операция не может зависеть от самой себя.",
            ),
            models.UniqueConstraint(
                fields=["predecessor", "successor"],
                name="sales_calc_dependency_unique_pair",
                violation_error_message="Такая связь уже есть.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.predecessor_id} → {self.successor_id}"
