"""Производственный заказ и визы его этапов (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.1, §2.3).

FSM-конвенция ИС: модель объявляет голые переходы, проверки, визы, журнал и события —
в `services/order.py`. `protected=True` не даёт сменить этап присваиванием мимо
`@transition`.

`inquiry_id`, `customer_id` — UUID без внешнего ключа (И2). Заказчик, номер заявки и
суммы калькуляции скопированы на момент запуска: доска и портфель читают много заказов
сразу, а соединять таблицы через границу модуля нельзя.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django_fsm import FSMField, transition

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import OrderStage
from .reference import ProductTemplate


@track()
class ProductionOrder(UUIDPrimaryKeyModel, TimeStampedModel):
    number = models.CharField("Номер", max_length=32, unique=True)
    inquiry_id = models.UUIDField("Заявка", null=True, blank=True)
    inquiry_number = models.CharField("Номер заявки", max_length=32, blank=True)
    customer_id = models.UUIDField("Заказчик (контрагент)", null=True, blank=True)
    customer_name = models.CharField("Заказчик", max_length=255)
    object_name = models.CharField("Объект", max_length=512, blank=True)
    product_name = models.CharField("Изделие", max_length=255)
    template = models.ForeignKey(
        ProductTemplate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Шаблон изделия",
    )
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=3)
    manager = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="managed_production_orders",
        verbose_name="Менеджер",
    )
    planned_start = models.DateField("Дата запуска")
    due_date = models.DateField("Срок по договору")
    stage = FSMField(
        "Этап",
        max_length=16,
        choices=OrderStage.choices,
        default=OrderStage.LAUNCH,
        protected=True,
    )
    contract_total = MoneyField(verbose_name="Сумма с НДС", default=Decimal("0"))
    labor_cost_planned = MoneyField(verbose_name="Плановая стоимость труда", default=Decimal("0"))
    shipped_at = models.DateTimeField("Отгружен", null=True, blank=True)

    class Meta:
        verbose_name = "Производственный заказ"
        verbose_name_plural = "Производственные заказы"
        ordering = ["-created_at"]
        permissions = [
            ("manage_orders", "Управление производственными заказами"),
            ("plan_operations", "Планирование операций заказа"),
            ("approve_any", "Виза за любого ответственного (замещение)"),
            ("manage_documents", "Документы заказа: загрузка, утверждение, аннулирование"),
        ]
        constraints = [
            # Один заказ на заявку — запуск идемпотентен и при гонке двух запросов.
            models.UniqueConstraint(
                fields=["inquiry_id"],
                condition=Q(inquiry_id__isnull=False),
                name="production_order_unique_inquiry",
                violation_error_message="По этой заявке производственный заказ уже создан.",
            ),
            models.CheckConstraint(
                name="production_order_quantity_positive",
                condition=Q(quantity__gt=0),
                violation_error_message="Количество должно быть больше нуля.",
            ),
            models.CheckConstraint(
                name="production_order_shipped_iff_done",
                condition=(
                    Q(stage=OrderStage.DONE, shipped_at__isnull=False)
                    | (~Q(stage=OrderStage.DONE) & Q(shipped_at__isnull=True))
                ),
                violation_error_message="Дата отгрузки есть ровно у отгруженного заказа.",
            ),
            models.CheckConstraint(
                name="production_order_money_non_negative",
                condition=Q(contract_total__gte=0, labor_cost_planned__gte=0),
                violation_error_message="Суммы заказа не могут быть отрицательными.",
            ),
        ]
        indexes = [models.Index(fields=["stage"], name="production_order_stage")]

    def __str__(self) -> str:
        return f"{self.number} — {self.product_name}"

    @transition(field=stage, source=OrderStage.LAUNCH, target=OrderStage.PREP)
    def to_prep(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.PREP, target=OrderStage.PROD)
    def to_prod(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.PROD, target=OrderStage.QC)
    def to_qc(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.QC, target=OrderStage.DONE)
    def to_done(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.PREP, target=OrderStage.LAUNCH)
    def back_to_launch(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.PROD, target=OrderStage.PREP)
    def back_to_prep(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.QC, target=OrderStage.PROD)
    def back_to_prod(self) -> None:
        pass

    @transition(field=stage, source=OrderStage.DONE, target=OrderStage.QC)
    def back_to_qc(self) -> None:
        pass


@track()
class OrderStageApproval(UUIDPrimaryKeyModel, TimeStampedModel):
    """Виза этапа — отметка «кто и когда», а не маршрут согласования (§2.3). Если визу
    поставил не ответственный (начальник производства за него), это видно по
    `approved_by != responsible`."""

    order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name="stage_approvals",
        verbose_name="Заказ",
    )
    stage = models.CharField("Этап", max_length=16, choices=OrderStage.choices)
    responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="production_stage_responsibilities",
        verbose_name="Ответственный",
    )
    approved_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="production_stage_approvals",
        verbose_name="Завизировал",
    )
    approved_at = models.DateTimeField("Дата визы", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Виза этапа заказа"
        verbose_name_plural = "Визы этапов заказа"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "stage"],
                name="production_stage_approval_unique",
                violation_error_message="Виза этого этапа у заказа уже заведена.",
            ),
            models.CheckConstraint(
                name="production_stage_approval_attribution",
                condition=(
                    Q(approved_by__isnull=True, approved_at__isnull=True)
                    | Q(approved_by__isnull=False, approved_at__isnull=False)
                ),
                violation_error_message="У визы есть и кто, и когда — или ни того, ни другого.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.stage}"
