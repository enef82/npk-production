"""Энергоресурсы и тарифы (§3.7).

`EnergyResource.tariff` — тариф, действующий сегодня; история — `TariffPeriod`.
Стоимость за прошлые сутки считается по периоду, действовавшему в те сутки; тариф
ресурса — запасной вариант для суток раньше первого периода. Оба значения пишет только
сервис `set_tariff`, поэтому они не расходятся.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class EnergyResource(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=16, unique=True)
    name = models.CharField("Наименование", max_length=128)
    unit = models.CharField("Единица измерения", max_length=16)
    tariff = MoneyField(verbose_name="Тариф за единицу", default=Decimal("0"))
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Энергоресурс"
        verbose_name_plural = "Энергоресурсы"
        ordering = ["order", "name"]
        permissions = [
            ("manage_meters", "Ведение счётчиков, тарифов и ручных показаний"),
            ("ingest_intervals", "Приём получасовых интервалов от SCADA"),
        ]
        constraints = [
            models.CheckConstraint(
                name="energy_resource_tariff_non_negative",
                condition=Q(tariff__gte=0),
                violation_error_message="Тариф не может быть отрицательным.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.unit}"


@track()
class TariffPeriod(UUIDPrimaryKeyModel, TimeStampedModel):
    resource = models.ForeignKey(
        EnergyResource,
        on_delete=models.CASCADE,
        related_name="tariff_periods",
        verbose_name="Ресурс",
    )
    valid_from = models.DateField("Действует с")
    tariff = MoneyField(verbose_name="Тариф за единицу")

    class Meta:
        verbose_name = "Период тарифа"
        verbose_name_plural = "Периоды тарифов"
        ordering = ["resource", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "valid_from"],
                name="energy_tariff_unique_start",
                violation_error_message="Тариф с этой даты уже задан.",
            ),
            models.CheckConstraint(
                name="energy_tariff_period_non_negative",
                condition=Q(tariff__gte=0),
                violation_error_message="Тариф не может быть отрицательным.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.resource_id} с {self.valid_from}: {self.tariff}"
