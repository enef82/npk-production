"""Справочники производства: участки, шаблоны изделий, настройки ответственных
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1). Правятся в админке.

Поле сортировки названо `sort_order`, а не `order`, как в спецификации: в модуле `order` —
это производственный заказ (`Operation.order`), и одно имя в двух смыслах читалось бы
неоднозначно.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import WorkPhase

# Единственная строка настроек — фиксированный ключ плюс CheckConstraint (прецедент
# `core.costing` ИС): вторую строку не создать ни админкой, ни кодом.
SETTINGS_ID = UUID("00000000-0000-7000-8000-000000000001")


@track()
class WorkCenter(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=32, unique=True)
    short_name = models.CharField("Краткое имя", max_length=8)
    name = models.CharField("Наименование", max_length=255)
    hourly_rate = MoneyField(verbose_name="Ставка нормо-часа", default=Decimal("0"))
    capacity = models.PositiveSmallIntegerField(
        "Мощность, исполнителей", default=1, help_text="Сколько человек работает одновременно"
    )
    responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="production_work_centers",
        verbose_name="Ответственный",
        help_text="Ответственный по умолчанию за операции участка",
    )
    phase = models.CharField("Фаза", max_length=8, choices=WorkPhase.choices)
    is_supply = models.BooleanField(
        "Снабжение",
        default=False,
        help_text="Трудоёмкость операций участка — срок поставки в днях; в часы и загрузку "
        "не входит",
    )
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Участок"
        verbose_name_plural = "Участки"
        ordering = ["sort_order", "code"]
        permissions = [
            ("manage_reference", "Ведение справочников производства"),
        ]
        constraints = [
            models.CheckConstraint(
                name="production_work_center_rate_non_negative",
                condition=Q(hourly_rate__gte=0),
                violation_error_message="Ставка не может быть отрицательной.",
            ),
            models.CheckConstraint(
                name="production_work_center_capacity",
                condition=Q(is_supply=True) | Q(capacity__gte=1),
                violation_error_message="У производственного участка хотя бы один исполнитель.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.short_name} — {self.name}"


@track()
class ProductTemplate(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField("Код", max_length=16, unique=True)
    name = models.CharField("Наименование", max_length=255)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Шаблон изделия"
        verbose_name_plural = "Шаблоны изделий"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


@track()
class TemplateMaterial(UUIDPrimaryKeyModel, TimeStampedModel):
    template = models.ForeignKey(
        ProductTemplate,
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name="Шаблон",
    )
    name = models.CharField("Наименование", max_length=255)
    qty_per_unit = models.DecimalField("Количество на единицу", max_digits=12, decimal_places=3)
    price = MoneyField(verbose_name="Цена")
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Материал шаблона"
        verbose_name_plural = "Материалы шаблона"
        ordering = ["template", "sort_order"]
        constraints = [
            models.CheckConstraint(
                name="production_template_material_qty_positive",
                condition=Q(qty_per_unit__gt=0),
                violation_error_message="Количество должно быть больше нуля.",
            ),
            models.CheckConstraint(
                name="production_template_material_price_non_negative",
                condition=Q(price__gte=0),
                violation_error_message="Цена не может быть отрицательной.",
            ),
        ]

    def __str__(self) -> str:
        return self.name


@track()
class TemplateOperation(UUIDPrimaryKeyModel, TimeStampedModel):
    template = models.ForeignKey(
        ProductTemplate,
        on_delete=models.CASCADE,
        related_name="operations",
        verbose_name="Шаблон",
    )
    seq = models.PositiveSmallIntegerField("Номер")
    name = models.CharField("Наименование", max_length=255)
    work_center = models.ForeignKey(
        WorkCenter,
        on_delete=models.PROTECT,
        related_name="template_operations",
        verbose_name="Участок",
    )
    hours = models.DecimalField(
        "Трудоёмкость, н-ч (снабжение — дни)", max_digits=10, decimal_places=2
    )
    scales_with_qty = models.BooleanField(
        "Зависит от количества", default=False, help_text="Трудоёмкость × количество изделий"
    )
    people = models.PositiveSmallIntegerField("Исполнителей", default=1)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Операция шаблона"
        verbose_name_plural = "Операции шаблона"
        ordering = ["template", "sort_order", "seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "seq"],
                name="production_template_operation_unique_seq",
                violation_error_message="Операция с таким номером в шаблоне уже есть.",
            ),
            models.CheckConstraint(
                name="production_template_operation_hours_non_negative",
                condition=Q(hours__gte=0),
                violation_error_message="Трудоёмкость не может быть отрицательной.",
            ),
            models.CheckConstraint(
                name="production_template_operation_people",
                condition=Q(people__gte=1),
                violation_error_message="Исполнителей — не меньше одного.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.seq} {self.name}"


@track()
class TemplateOperationDependency(UUIDPrimaryKeyModel, TimeStampedModel):
    """Обе операции — одного шаблона: проверяет триггер миграции
    `0002_template_dependency_same_template`, `CheckConstraint` соседнюю строку не видит."""

    predecessor = models.ForeignKey(
        TemplateOperation,
        on_delete=models.CASCADE,
        related_name="successor_links",
        verbose_name="Предшественник",
    )
    successor = models.ForeignKey(
        TemplateOperation,
        on_delete=models.CASCADE,
        related_name="predecessor_links",
        verbose_name="Последователь",
    )

    class Meta:
        verbose_name = "Связь операций шаблона"
        verbose_name_plural = "Связи операций шаблона"
        constraints = [
            models.CheckConstraint(
                name="production_template_dependency_not_self",
                condition=~Q(predecessor=models.F("successor")),
                violation_error_message="Операция не может зависеть от самой себя.",
            ),
            models.UniqueConstraint(
                fields=["predecessor", "successor"],
                name="production_template_dependency_unique_pair",
                violation_error_message="Такая связь уже есть.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.predecessor_id} → {self.successor_id}"


@track()
class ProductionSettings(TimeStampedModel):
    """Ответственные за этапы заказа по умолчанию (§3.1). Этап «Отгружено» — всегда
    менеджер заказа, поэтому здесь его нет."""

    id = models.UUIDField("Идентификатор", primary_key=True, default=SETTINGS_ID, editable=False)
    launch_responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Запуск в работу",
    )
    prep_responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Подготовка производства",
    )
    prod_responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Изготовление",
    )
    qc_responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="ОТК и испытания",
    )

    class Meta:
        verbose_name = "Настройки производства"
        verbose_name_plural = "Настройки производства"
        constraints = [
            models.CheckConstraint(
                name="production_settings_singleton",
                condition=Q(id=SETTINGS_ID),
                violation_error_message="Настройки производства — одна запись.",
            ),
        ]

    def __str__(self) -> str:
        return "Настройки производства"
