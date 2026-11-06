"""Справочники и настройки заявок (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2, §7 п.1).
Правятся в админке."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

SETTINGS_ID = UUID("00000000-0000-7000-8000-000000000002")


@track()
class LossReason(UUIDPrimaryKeyModel, TimeStampedModel):
    """Причина проигрыша — справочник, а не строка: по причинам строится отчёт
    (CLAUDE.md §5, спецификация §7 п.1)."""

    name = models.CharField("Наименование", max_length=255, unique=True)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Причина проигрыша"
        verbose_name_plural = "Причины проигрыша"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


@track()
class SalesSettings(TimeStampedModel):
    """Экономист — ответственный за этап «Просчёт» по умолчанию; вероятности этапов —
    взвешивание воронки в портфеле."""

    id = models.UUIDField("Идентификатор", primary_key=True, default=SETTINGS_ID, editable=False)
    economist = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Экономист",
    )
    prob_new = models.DecimalField(
        "Вероятность: новые, %", max_digits=5, decimal_places=2, default=Decimal("10")
    )
    prob_calc = models.DecimalField(
        "Вероятность: просчёт, %", max_digits=5, decimal_places=2, default=Decimal("30")
    )
    prob_approval = models.DecimalField(
        "Вероятность: согласование КП, %", max_digits=5, decimal_places=2, default=Decimal("60")
    )

    class Meta:
        verbose_name = "Настройки заявок"
        verbose_name_plural = "Настройки заявок"
        constraints = [
            models.CheckConstraint(
                name="sales_settings_singleton",
                condition=Q(id=SETTINGS_ID),
                violation_error_message="Настройки заявок — одна запись.",
            ),
            models.CheckConstraint(
                name="sales_settings_probabilities",
                condition=(
                    Q(prob_new__gte=0, prob_new__lte=100)
                    & Q(prob_calc__gte=0, prob_calc__lte=100)
                    & Q(prob_approval__gte=0, prob_approval__lte=100)
                ),
                violation_error_message="Вероятность — от 0 до 100 %.",
            ),
        ]

    def __str__(self) -> str:
        return "Настройки заявок"
