"""Заявка на просчёт и визы её этапов (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2).

`customer_id` — UUID `Party` ядра (И2), `customer_name` — копия для доски; `template_id`
и `order_id` — UUID шаблона и заказа модуля `production` без внешнего ключа (И2).
FSM-конвенция ИС: модель объявляет голые переходы, проверки и события — в сервисах.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django_fsm import FSMField, transition

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import OPEN_STAGES, InquiryStage
from .reference import LossReason


@track()
class Inquiry(UUIDPrimaryKeyModel, TimeStampedModel):
    number = models.CharField("Номер", max_length=32, unique=True)
    customer_id = models.UUIDField("Заказчик (контрагент)")
    customer_name = models.CharField("Заказчик", max_length=255)
    object_name = models.CharField("Объект", max_length=512, blank=True)
    template_id = models.UUIDField("Шаблон изделия", null=True, blank=True)
    product_name = models.CharField("Изделие", max_length=255, blank=True)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=3)
    due_date = models.DateField("Требуемый срок")
    manager = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="sales_inquiries",
        verbose_name="Менеджер",
    )
    stage = FSMField(
        "Этап",
        max_length=16,
        choices=InquiryStage.choices,
        default=InquiryStage.NEW,
        protected=True,
    )
    planned_start = models.DateField("Предварительный старт", null=True, blank=True)
    overhead_pct = models.DecimalField(
        "Накладные, %", max_digits=5, decimal_places=2, default=Decimal("25")
    )
    margin_pct = models.DecimalField(
        "Наценка, %", max_digits=5, decimal_places=2, default=Decimal("20")
    )
    vat_pct = models.DecimalField("НДС, %", max_digits=5, decimal_places=2, default=Decimal("22"))
    order_id = models.UUIDField("Производственный заказ", null=True, blank=True)
    lost_reason = models.ForeignKey(
        LossReason,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inquiries",
        verbose_name="Причина проигрыша",
    )
    lost_comment = models.TextField("Комментарий к проигрышу", blank=True)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]
        permissions = [
            ("manage_inquiries", "Ведение своих заявок"),
            ("manage_calculation", "Калькуляция заявок"),
            ("launch_inquiry", "Запуск заявки в производство"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["order_id"],
                condition=Q(order_id__isnull=False),
                name="sales_inquiry_unique_order",
                violation_error_message="Этот заказ уже связан с другой заявкой.",
            ),
            models.CheckConstraint(
                name="sales_inquiry_quantity_positive",
                condition=Q(quantity__gt=0),
                violation_error_message="Количество должно быть больше нуля.",
            ),
            models.CheckConstraint(
                name="sales_inquiry_percents",
                condition=(
                    Q(overhead_pct__gte=0, margin_pct__gte=0) & Q(vat_pct__gte=0, vat_pct__lte=100)
                ),
                violation_error_message="Проценты калькуляции не могут быть отрицательными.",
            ),
            models.CheckConstraint(
                name="sales_inquiry_launched_iff_order",
                condition=(
                    Q(stage=InquiryStage.LAUNCHED, order_id__isnull=False)
                    | (~Q(stage=InquiryStage.LAUNCHED) & Q(order_id__isnull=True))
                ),
                violation_error_message="Заказ есть ровно у запущенной заявки.",
            ),
            models.CheckConstraint(
                name="sales_inquiry_lost_iff_reason",
                condition=(
                    Q(stage=InquiryStage.LOST, lost_reason__isnull=False)
                    | (~Q(stage=InquiryStage.LOST) & Q(lost_reason__isnull=True))
                ),
                violation_error_message="Причина есть ровно у проигранной заявки.",
            ),
        ]
        indexes = [models.Index(fields=["stage"], name="sales_inquiry_stage")]

    def __str__(self) -> str:
        return f"{self.number} — {self.customer_name}"

    @transition(field=stage, source=InquiryStage.NEW, target=InquiryStage.CALC)
    def to_calc(self) -> None:
        pass

    @transition(field=stage, source=InquiryStage.CALC, target=InquiryStage.APPROVAL)
    def to_approval(self) -> None:
        pass

    @transition(field=stage, source=InquiryStage.CALC, target=InquiryStage.NEW)
    def back_to_new(self) -> None:
        pass

    @transition(field=stage, source=InquiryStage.APPROVAL, target=InquiryStage.CALC)
    def back_to_calc(self) -> None:
        pass

    @transition(field=stage, source=InquiryStage.APPROVAL, target=InquiryStage.LAUNCHED)
    def mark_launched(self) -> None:
        pass

    @transition(field=stage, source=list(OPEN_STAGES), target=InquiryStage.LOST)
    def mark_lost(self) -> None:
        pass


@track()
class InquiryStageApproval(UUIDPrimaryKeyModel, TimeStampedModel):
    """Виза этапа заявки — отметка «кто и когда» (§2.3)."""

    inquiry = models.ForeignKey(
        Inquiry,
        on_delete=models.CASCADE,
        related_name="stage_approvals",
        verbose_name="Заявка",
    )
    stage = models.CharField("Этап", max_length=16, choices=InquiryStage.choices)
    responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_stage_responsibilities",
        verbose_name="Ответственный",
    )
    approved_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_stage_approvals",
        verbose_name="Завизировал",
    )
    approved_at = models.DateTimeField("Дата визы", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Виза этапа заявки"
        verbose_name_plural = "Визы этапов заявки"
        constraints = [
            models.UniqueConstraint(
                fields=["inquiry", "stage"],
                name="sales_stage_approval_unique",
                violation_error_message="Виза этого этапа у заявки уже заведена.",
            ),
            models.CheckConstraint(
                name="sales_stage_approval_stage",
                condition=Q(stage__in=list(OPEN_STAGES)),
                violation_error_message="Визы есть только у этапов «Новые», «Просчёт», «КП».",
            ),
            models.CheckConstraint(
                name="sales_stage_approval_attribution",
                condition=(
                    Q(approved_by__isnull=True, approved_at__isnull=True)
                    | Q(approved_by__isnull=False, approved_at__isnull=False)
                ),
                violation_error_message="У визы есть и кто, и когда — или ни того, ни другого.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.inquiry_id}: {self.stage}"
