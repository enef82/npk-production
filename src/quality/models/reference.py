"""Справочники ОТК: точки контроля участков, виды дефектов точки, причины брака
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3).

`work_center_id` — UUID участка модуля `production` без внешнего ключа (И2). По видам
дефектов и причинам строится Парето — поэтому это справочники, а не свободный текст
(CLAUDE.md §5).
"""

from __future__ import annotations

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class InspectionPoint(UUIDPrimaryKeyModel, TimeStampedModel):
    work_center_id = models.UUIDField("Участок", unique=True)
    name = models.CharField("Наименование", max_length=255)
    is_final = models.BooleanField(
        "Финальный контроль",
        default=False,
        help_text="Приёмо-сдаточный контроль: брак здесь выявлен поздно",
    )
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Точка контроля"
        verbose_name_plural = "Точки контроля"
        ordering = ["is_final", "name"]
        permissions = [
            ("record_inspection", "Запись результатов контроля операций"),
            ("manage_reference", "Ведение справочников ОТК"),
        ]

    def __str__(self) -> str:
        return self.name


@track()
class DefectType(UUIDPrimaryKeyModel, TimeStampedModel):
    inspection_point = models.ForeignKey(
        InspectionPoint,
        on_delete=models.CASCADE,
        related_name="defect_types",
        verbose_name="Точка контроля",
    )
    name = models.CharField("Наименование", max_length=255)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Вид дефекта"
        verbose_name_plural = "Виды дефектов"
        ordering = ["inspection_point", "order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["inspection_point", "name"],
                name="quality_defect_type_unique_name",
                violation_error_message="Такой вид дефекта у точки контроля уже есть.",
            ),
        ]

    def __str__(self) -> str:
        return self.name


@track()
class DefectCause(UUIDPrimaryKeyModel, TimeStampedModel):
    """Причина брака. `is_operator_fault` — признак «по вине оператора» для выработки
    сотрудника (§3.3, §3.8): отчёт берёт причину по признаку, а не по совпадению
    названия (тот же приём, что `equipment.DownReason.repair_kind`)."""

    name = models.CharField("Наименование", max_length=128, unique=True)
    is_operator_fault = models.BooleanField("По вине оператора", default=False)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Действует", default=True)

    class Meta:
        verbose_name = "Причина брака"
        verbose_name_plural = "Причины брака"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name
