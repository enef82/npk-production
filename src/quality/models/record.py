"""Запись контроля операции (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3).

`operation_id`, `order_id`, `work_center_id` — UUID сущностей `production` без внешних
ключей (И2). Заказ и участок — копии на момент записи: отчёты по участку и неделе
считаются без обращения к чужому модулю.

Количества — целые штуки (проверено, доработка, списание): контроль считает изделия
и детали поштучно, как прототип (`qcAgg`); дробная «проверенная деталь» смысла не имеет.
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .reference import DefectCause, DefectType


@track()
class InspectionRecord(UUIDPrimaryKeyModel, TimeStampedModel):
    operation_id = models.UUIDField("Операция")
    order_id = models.UUIDField("Заказ")
    work_center_id = models.UUIDField("Участок")
    date = models.DateField("Дата")
    inspector = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="inspection_records",
        verbose_name="Контролёр",
    )
    checked = models.PositiveIntegerField("Проверено, шт.")
    rework = models.PositiveIntegerField("Брак: доработка, шт.", default=0)
    scrap = models.PositiveIntegerField("Брак: списание, шт.", default=0)
    defect_type = models.ForeignKey(
        DefectType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="records",
        verbose_name="Вид дефекта",
    )
    cause = models.ForeignKey(
        DefectCause,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="records",
        verbose_name="Причина",
    )
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Запись контроля"
        verbose_name_plural = "Записи контроля"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["operation_id"], name="quality_record_operation"),
            models.Index(fields=["date", "work_center_id"], name="quality_record_week"),
        ]
        constraints = [
            models.CheckConstraint(
                name="quality_record_checked_positive",
                condition=Q(checked__gt=0),
                violation_error_message="Проверено должно быть больше нуля.",
            ),
            models.CheckConstraint(
                name="quality_record_defects_within_checked",
                condition=Q(rework__lte=F("checked") - F("scrap")),
                violation_error_message="Брака больше, чем проверено.",
            ),
            # Брак без вида и причины не попадает в Парето — а ради него брак и вносят.
            models.CheckConstraint(
                name="quality_record_defect_classified",
                condition=(
                    Q(rework=0, scrap=0) | Q(defect_type__isnull=False, cause__isnull=False)
                ),
                violation_error_message="Для брака укажите вид дефекта и причину.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date}: проверено {self.checked}, брак {self.rework + self.scrap}"

    @property
    def defects(self) -> int:
        return self.rework + self.scrap
