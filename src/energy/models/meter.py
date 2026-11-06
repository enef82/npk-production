"""Счётчики, получасовые интервалы, ручные показания, журнал пакетов SCADA (§3.7).

`equipment_id` — UUID оборудования модуля `equipment` без внешнего ключа (И2).
Дерево счётчиков — FK на себя; что родитель того же ресурса и что дерево без циклов,
проверяет сервис (`services/meter.py`).
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Extract, Mod
from django.db.models.lookups import Exact

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import MeterKind, MeterSource
from .resource import EnergyResource


@track()
class Meter(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=32, unique=True)
    name = models.CharField("Наименование", max_length=255)
    resource = models.ForeignKey(
        EnergyResource, on_delete=models.PROTECT, related_name="meters", verbose_name="Ресурс"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительский счётчик",
    )
    kind = models.CharField("Вид точки учёта", max_length=16, choices=MeterKind.choices)
    equipment_id = models.UUIDField("Оборудование", null=True, blank=True)
    source = models.CharField(
        "Источник данных", max_length=16, choices=MeterSource.choices, default=MeterSource.SCADA
    )
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Счётчик"
        verbose_name_plural = "Счётчики"
        ordering = ["resource__order", "order", "code"]
        constraints = [
            models.CheckConstraint(
                name="energy_meter_not_own_parent",
                condition=Q(parent__isnull=True) | ~Q(parent=F("id")),
                violation_error_message="Счётчик не может быть родителем самому себе.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class MeterInterval(UUIDPrimaryKeyModel):
    """Получасовой расход. Без `TimeStampedModel` и без истории pghistory: 48 строк
    в сутки на счётчик, приходят машинным потоком; кто и когда прислал — журнал
    `ScadaMessage`, ручной ввод — `MeterReading` (у него история есть)."""

    meter = models.ForeignKey(
        Meter, on_delete=models.CASCADE, related_name="intervals", verbose_name="Счётчик"
    )
    start = models.DateTimeField("Начало интервала")
    value = models.DecimalField("Расход", max_digits=16, decimal_places=4)
    source = models.CharField(
        "Источник", max_length=16, choices=MeterSource.choices, default=MeterSource.SCADA
    )

    class Meta:
        verbose_name = "Получасовой интервал"
        verbose_name_plural = "Получасовые интервалы"
        ordering = ["meter", "start"]
        constraints = [
            models.UniqueConstraint(
                fields=["meter", "start"],
                name="energy_interval_unique_start",
                violation_error_message="Интервал с таким началом у счётчика уже есть.",
            ),
            # Начало кратно 30 минутам: остаток эпохи (в секундах) от деления на 1800 —
            # ноль; дробные секунды тоже дают ненулевой остаток. Django считает эпоху
            # после перевода в TIME_ZONE проекта (`AT TIME ZONE`), смещение
            # Europe/Moscow — целые часы, поэтому кратность 30 минутам сохраняется.
            models.CheckConstraint(
                name="energy_interval_start_half_hour",
                condition=Exact(Mod(Extract("start", "epoch"), 1800), 0),
                violation_error_message="Начало интервала должно быть кратно 30 минутам.",
            ),
            models.CheckConstraint(
                name="energy_interval_value_non_negative",
                condition=Q(value__gte=0),
                violation_error_message="Расход не может быть отрицательным.",
            ),
        ]
        indexes = [models.Index(fields=["start"], name="energy_interval_start")]

    def __str__(self) -> str:
        return f"{self.meter_id} {self.start:%Y-%m-%d %H:%M}: {self.value}"


@track()
class MeterReading(UUIDPrimaryKeyModel, TimeStampedModel):
    """Показание счётчика ручного учёта (накопительное). Расход между двумя
    показаниями сервис раскладывает в получасовые интервалы — отчёты читают только
    интервалы, одинаково для SCADA и ручного ввода."""

    meter = models.ForeignKey(
        Meter, on_delete=models.CASCADE, related_name="readings", verbose_name="Счётчик"
    )
    taken_at = models.DateTimeField("Время снятия")
    value = models.DecimalField("Показание", max_digits=16, decimal_places=4)

    class Meta:
        verbose_name = "Показание счётчика"
        verbose_name_plural = "Показания счётчиков"
        ordering = ["meter", "-taken_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["meter", "taken_at"],
                name="energy_reading_unique_time",
                violation_error_message="Показание на это время уже внесено.",
            ),
            models.CheckConstraint(
                name="energy_reading_non_negative",
                condition=Q(value__gte=0),
                violation_error_message="Показание не может быть отрицательным.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.meter_id} {self.taken_at:%Y-%m-%d %H:%M}: {self.value}"


@track()
class ScadaMessage(UUIDPrimaryKeyModel, TimeStampedModel):
    """Журнал принятых пакетов: уникальность `message_id` — то, на чём держится
    идемпотентность приёма (повторная доставка пакета не меняет данных)."""

    message_id = models.CharField("Идентификатор пакета", max_length=64, unique=True)
    source_id = models.CharField("Источник (узел SCADA)", max_length=64)
    schema_version = models.CharField("Версия формата", max_length=16)
    items_total = models.PositiveIntegerField("Строк в пакете")
    items_accepted = models.PositiveIntegerField("Принято строк")
    items_rejected = models.PositiveIntegerField("Отклонено строк")
    errors = models.JSONField("Отклонённые строки", default=list, blank=True)

    class Meta:
        verbose_name = "Пакет SCADA"
        verbose_name_plural = "Пакеты SCADA"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.source_id}: {self.message_id}"
