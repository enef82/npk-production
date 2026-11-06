"""Оборудование, суточная наработка и техническое обслуживание (§3.6).

`work_center_id` — UUID участка модуля `production` без внешнего ключа (И2).
Моточасы не хранятся: наработка = `operating_hours_initial` + Σ `RuntimeLog.run`
(селектор) — хранимая копия разошлась бы с журналом на первой правке смены.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import F, Q

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import EquipmentStatus, RuntimeSource
from .reference import DownReason, IdleReason


@track()
class Equipment(UUIDPrimaryKeyModel, TimeStampedModel):
    inventory_no = models.CharField("Инвентарный номер", max_length=32, unique=True)
    name = models.CharField("Наименование", max_length=255)
    work_center_id = models.UUIDField("Участок", null=True, blank=True)
    control_system = models.CharField("Система управления", max_length=128, blank=True)
    connection = models.CharField("Способ подключения", max_length=255, blank=True)
    status = models.CharField(
        "Состояние", max_length=16, choices=EquipmentStatus.choices, default=EquipmentStatus.RUN
    )
    operating_hours_initial = models.DecimalField(
        "Моточасы на начало учёта", default=Decimal("0"), max_digits=12, decimal_places=2
    )

    class Meta:
        verbose_name = "Оборудование"
        verbose_name_plural = "Оборудование"
        ordering = ["inventory_no"]
        permissions = [
            ("manage_equipment", "Ведение оборудования, ТО и ремонтов"),
            ("log_runtime", "Ввод наработки за смену и регистрация отказов"),
        ]
        constraints = [
            models.CheckConstraint(
                name="equipment_initial_hours_non_negative",
                condition=Q(operating_hours_initial__gte=0),
                violation_error_message="Начальные моточасы не могут быть отрицательными.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.inventory_no} — {self.name}"


@track()
class RuntimeLog(UUIDPrimaryKeyModel, TimeStampedModel):
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="runtime_logs",
        verbose_name="Оборудование",
    )
    date = models.DateField("Дата")
    run = models.DecimalField("Работа, ч", default=Decimal("0"), max_digits=5, decimal_places=2)
    setup = models.DecimalField("Наладка, ч", default=Decimal("0"), max_digits=5, decimal_places=2)
    idle = models.DecimalField("Простой, ч", default=Decimal("0"), max_digits=5, decimal_places=2)
    down = models.DecimalField("Отказ, ч", default=Decimal("0"), max_digits=5, decimal_places=2)
    idle_reason = models.ForeignKey(
        IdleReason,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="runtime_logs",
        verbose_name="Причина простоя",
    )
    down_reason = models.ForeignKey(
        DownReason,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="runtime_logs",
        verbose_name="Причина остановки",
    )
    source = models.CharField(
        "Источник", max_length=16, choices=RuntimeSource.choices, default=RuntimeSource.MANUAL
    )

    class Meta:
        verbose_name = "Наработка за сутки"
        verbose_name_plural = "Наработка по суткам"
        ordering = ["equipment", "-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "date"],
                name="equipment_runtime_unique_day",
                violation_error_message="Наработка за эти сутки уже внесена.",
            ),
            models.CheckConstraint(
                name="equipment_runtime_non_negative",
                condition=Q(run__gte=0, setup__gte=0, idle__gte=0, down__gte=0),
                violation_error_message="Часы наработки не могут быть отрицательными.",
            ),
            models.CheckConstraint(
                name="equipment_runtime_max_24h",
                condition=Q(run__lte=24 - F("setup") - F("idle") - F("down")),
                violation_error_message="Больше 24 ч в сутки.",
            ),
            # Без причины простой не попадает в Парето — а ради него простой и вносят.
            models.CheckConstraint(
                name="equipment_runtime_idle_reason",
                condition=Q(idle=0) | Q(idle_reason__isnull=False),
                violation_error_message="Укажите причину простоя.",
            ),
            models.CheckConstraint(
                name="equipment_runtime_down_reason",
                condition=Q(down=0) | Q(down_reason__isnull=False),
                violation_error_message="Укажите причину остановки.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.equipment_id} {self.date}: {self.run} ч"


@track()
class MaintenanceType(UUIDPrimaryKeyModel, TimeStampedModel):
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="maintenance_types",
        verbose_name="Оборудование",
    )
    code = models.CharField("Вид ТО", max_length=16)
    interval_hours = models.DecimalField("Интервал, моточасы", max_digits=12, decimal_places=2)
    scope = models.TextField("Состав работ", blank=True)

    class Meta:
        verbose_name = "Вид ТО"
        verbose_name_plural = "Виды ТО"
        ordering = ["equipment", "interval_hours", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "code"],
                name="equipment_maintenance_type_unique_code",
                violation_error_message="Такой вид ТО у оборудования уже есть.",
            ),
            models.CheckConstraint(
                name="equipment_maintenance_interval_positive",
                condition=Q(interval_hours__gt=0),
                violation_error_message="Интервал ТО должен быть больше нуля.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.interval_hours} ч)"


@track()
class MaintenanceRecord(UUIDPrimaryKeyModel, TimeStampedModel):
    maintenance_type = models.ForeignKey(
        MaintenanceType, on_delete=models.CASCADE, related_name="records", verbose_name="Вид ТО"
    )
    date = models.DateField("Дата")
    at_hours = models.DecimalField("При наработке, моточасы", max_digits=12, decimal_places=2)
    performed_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="maintenance_records",
        verbose_name="Исполнитель",
    )

    class Meta:
        verbose_name = "Проведённое ТО"
        verbose_name_plural = "Проведённые ТО"
        ordering = ["maintenance_type", "-date"]
        constraints = [
            models.CheckConstraint(
                name="equipment_maintenance_record_hours_non_negative",
                condition=Q(at_hours__gte=0),
                violation_error_message="Моточасы не могут быть отрицательными.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.maintenance_type_id} {self.date} при {self.at_hours} ч"
