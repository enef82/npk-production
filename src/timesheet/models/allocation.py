"""Разноска — первичный ввод табеля (И7): сотрудник, день, вид времени, объект, часы.
Свод табеля и итоги по объектам — селекторы, хранимого `TimesheetEntry` нет.

`order_id`, `operation_id` — UUID заказа и операции модуля `production` без внешнего
ключа (И2). «Не больше 24 ч в день на сотрудника» — сумма по нескольким строкам,
проверяется сервисом под блокировкой периода; в БД — только «строка ≤ 24 ч».
"""

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import AllocationSource, AllocationTarget


@track()
class WorkAllocation(UUIDPrimaryKeyModel, TimeStampedModel):
    employee = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="work_allocations",
        verbose_name="Сотрудник",
    )
    date = models.DateField("Дата")
    time_code = models.ForeignKey(
        "timesheet.TimeCode",
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="Вид времени",
    )
    # Пусто — у неразносимых кодов (отпуск, больничный): часы есть, объекта нет.
    target = models.CharField("Объект", max_length=16, choices=AllocationTarget.choices, blank=True)
    order_id = models.UUIDField("Заказ", null=True, blank=True)
    operation_id = models.UUIDField("Операция", null=True, blank=True)
    hours = models.DecimalField("Часы", max_digits=10, decimal_places=2)
    source = models.CharField(
        "Источник", max_length=16, choices=AllocationSource.choices, default=AllocationSource.MANUAL
    )
    source_ref = models.CharField("Основание", max_length=64, blank=True)

    class Meta:
        verbose_name = "Разноска"
        verbose_name_plural = "Разноска"
        ordering = ["employee", "date", "created_at"]
        indexes = [
            models.Index(fields=["employee", "date"], name="timesheet_alloc_emp_date"),
            models.Index(fields=["date"], name="timesheet_alloc_date"),
            models.Index(fields=["order_id"], name="timesheet_alloc_order"),
        ]
        constraints = [
            models.CheckConstraint(
                name="timesheet_alloc_hours_range",
                condition=Q(hours__gt=0, hours__lte=24),
                violation_error_message="Часы строки — больше нуля и не больше 24.",
            ),
            models.CheckConstraint(
                name="timesheet_alloc_order_target",
                condition=(Q(target=AllocationTarget.ORDER) & Q(order_id__isnull=False))
                | (~Q(target=AllocationTarget.ORDER) & Q(order_id__isnull=True)),
                violation_error_message=(
                    "Заказ указывается тогда и только тогда, когда объект — заказ."
                ),
            ),
            models.CheckConstraint(
                name="timesheet_alloc_operation_needs_order",
                condition=Q(operation_id__isnull=True) | Q(order_id__isnull=False),
                violation_error_message="Операция указывается только вместе с заказом.",
            ),
            models.CheckConstraint(
                name="timesheet_alloc_repair_has_ref",
                condition=~Q(source=AllocationSource.REPAIR) | ~Q(source_ref=""),
                violation_error_message="Разноска из ремонта ссылается на номер ремонта.",
            ),
            # Идемпотентность обработчика `equipment.repair_closed`: по одному ремонту
            # у сотрудника — одна строка, даже при гонке двух доставок.
            models.UniqueConstraint(
                fields=["employee", "source_ref"],
                condition=Q(source=AllocationSource.REPAIR),
                name="timesheet_alloc_repair_unique",
                violation_error_message="Часы этого ремонта у сотрудника уже разнесены.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.date}: {self.hours} ч"
