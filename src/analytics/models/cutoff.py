"""Недельная отсечка (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8; прототип
`S.cuts`, `seedCuts`).

Снимок неизменяем: строки после закрытия не правятся (триггер БД
`0002_cutoff_snapshot_immutable`), переоткрытие — удаление снимка с причиной в журнале
`WeeklyCutoffEvent`. Журнал хранится отдельно от снимка: после переоткрытия снимка уже
нет, а «кто, когда и почему переоткрыл» должно остаться.

`work_center_id` — UUID участка `production` без внешнего ключа (И2).
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q

from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


class CutoffAction(models.TextChoices):
    CLOSE = "close", "Закрытие"
    REOPEN = "reopen", "Переоткрытие"


class WeeklyCutoff(UUIDPrimaryKeyModel, TimeStampedModel):
    week_start = models.DateField("Неделя (понедельник)", unique=True)
    closed_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="closed_cutoffs",
        verbose_name="Закрыл",
    )
    closed_at = models.DateTimeField("Закрыта")
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Недельная отсечка"
        verbose_name_plural = "Недельные отсечки"
        ordering = ["-week_start"]
        permissions = [
            ("close_cutoff", "Закрытие и переоткрытие недельных отсечек"),
        ]
        constraints = [
            # Неделя адресуется понедельником: иначе одна неделя могла бы закрыться
            # дважды под разными датами.
            models.CheckConstraint(
                name="analytics_cutoff_week_starts_monday",
                condition=Q(week_start__iso_week_day=1),
                violation_error_message="Неделя отсечки начинается с понедельника.",
            ),
        ]

    def __str__(self) -> str:
        return f"Отсечка недели с {self.week_start:%d.%m.%Y}"


class WeeklyCutoffRow(UUIDPrimaryKeyModel):
    cutoff = models.ForeignKey(
        WeeklyCutoff,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="Отсечка",
    )
    work_center_id = models.UUIDField("Участок")
    planned_hours = models.DecimalField("План, н-ч", max_digits=10, decimal_places=2)
    # Освоение может быть отрицательным: откат прогресса сторнирует часы (§3.1).
    earned_hours = models.DecimalField("Освоено, н-ч", max_digits=10, decimal_places=2)
    worked_hours = models.DecimalField("Отработано, ч", max_digits=10, decimal_places=2)
    checked = models.PositiveIntegerField("Проверено, шт.")
    defects = models.PositiveIntegerField("Брак, шт.")

    class Meta:
        verbose_name = "Строка отсечки"
        verbose_name_plural = "Строки отсечки"
        constraints = [
            models.UniqueConstraint(
                fields=["cutoff", "work_center_id"], name="analytics_cutoff_row_unique_wc"
            ),
            models.CheckConstraint(
                name="analytics_cutoff_row_hours_non_negative",
                condition=Q(planned_hours__gte=0, worked_hours__gte=0),
                violation_error_message="План и отработанные часы не могут быть отрицательными.",
            ),
            models.CheckConstraint(
                name="analytics_cutoff_row_defects_within_checked",
                condition=Q(defects__lte=F("checked")),
                violation_error_message="Брака больше, чем проверено.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cutoff}: участок {self.work_center_id}"


class WeeklyCutoffEvent(UUIDPrimaryKeyModel):
    week_start = models.DateField("Неделя (понедельник)")
    action = models.CharField("Действие", max_length=16, choices=CutoffAction.choices)
    actor = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="cutoff_events",
        verbose_name="Кто",
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    # Для закрытия — комментарий недели, для переоткрытия — причина (обязательна).
    text = models.TextField("Комментарий или причина", blank=True)

    class Meta:
        verbose_name = "Событие отсечки"
        verbose_name_plural = "Журнал отсечек"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["week_start"], name="analytics_cutoff_event_week")]
        constraints = [
            models.CheckConstraint(
                name="analytics_cutoff_event_reopen_has_reason",
                condition=~Q(action=CutoffAction.REOPEN) | ~Q(text=""),
                violation_error_message="Переоткрытие отсечки — только с причиной.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} недели с {self.week_start:%d.%m.%Y}"
