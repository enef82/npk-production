"""Справочники модуля «Оборудование и ТО»: причины простоя, причины отказа (остановки),
категории отказов. По ним строится Парето простоев и статистика аварий — поэтому это
справочники, а не свободный текст (CLAUDE.md §5)."""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import RepairKind


class _Reference(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField("Наименование", max_length=128, unique=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        abstract = True
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


@track()
class IdleReason(_Reference):
    class Meta(_Reference.Meta):
        verbose_name = "Причина простоя"
        verbose_name_plural = "Причины простоя"


@track()
class DownReason(_Reference):
    """Причина остановки (отказ, ТО, ремонт). `repair_kind` связывает причину с видом
    записи журнала ремонтов: при закрытии ремонта простой ложится в наработку суток
    с этой причиной — по связи, а не по совпадению названия."""

    repair_kind = models.CharField(
        "Вид записи ремонта", max_length=16, choices=RepairKind.choices, blank=True
    )

    class Meta(_Reference.Meta):
        verbose_name = "Причина остановки"
        verbose_name_plural = "Причины остановки"
        constraints = [
            models.UniqueConstraint(
                fields=["repair_kind"],
                condition=~Q(repair_kind=""),
                name="equipment_down_reason_unique_kind",
                violation_error_message="Для этого вида ремонта причина остановки уже задана.",
            ),
        ]


@track()
class FailureCategory(_Reference):
    class Meta(_Reference.Meta):
        verbose_name = "Категория отказа"
        verbose_name_plural = "Категории отказов"
