"""Код вида времени (Я, РВ, С, …) — справочник, по которому строится табель для 1С и
стоимость часов (`cost_multiplier`). Засеивается миграцией `0002_seed_time_codes`."""

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class TimeCode(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код 1С", max_length=8, unique=True)
    name = models.CharField("Наименование", max_length=128)
    is_work = models.BooleanField("Рабочее время", default=True)
    is_allocatable = models.BooleanField(
        "Разносится на объекты",
        default=True,
        help_text="Часы с этим кодом разносятся на заказ, накладные, ремонт и т. п.",
    )
    cost_multiplier = models.DecimalField(
        "Коэффициент стоимости", max_digits=4, decimal_places=2, default=1
    )
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Код вида времени"
        verbose_name_plural = "Коды видов времени"
        ordering = ["sort_order", "code"]
        constraints = [
            models.CheckConstraint(
                name="timesheet_timecode_multiplier_positive",
                condition=Q(cost_multiplier__gt=0),
                violation_error_message="Коэффициент стоимости должен быть больше нуля.",
            ),
            # Разносится только рабочее время: отпуск или больничный на заказ не ложатся.
            models.CheckConstraint(
                name="timesheet_timecode_allocatable_is_work",
                condition=Q(is_allocatable=False) | Q(is_work=True),
                violation_error_message="Разносить на объекты можно только рабочее время.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"
