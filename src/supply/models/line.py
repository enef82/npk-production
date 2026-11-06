"""Строка потребности и её история (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4).

`order_id`, `operation_id` — UUID сущностей `production` без внешних ключей (И2); строка
без заказа — заявка «на склад / ТО». Статус — FSM с защитой от прямого присваивания:
переходы (`prAction` прототипа) выполняют только сервисы, проверка ролей — в API.

Номер заявки (`requisition_no`) — строка, общая для пачки строк, переданных в закупку
одним действием: сама заявка отдельной сущности не имеет — у неё нет ни своего
состояния, ни своих полей, кроме номера (реестр заявок — группировка в селекторе).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_fsm import FSMField, transition

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import LineCategory, LineKind, LineStatus
from .reference import Supplier


@track()
class PurchaseLine(UUIDPrimaryKeyModel, TimeStampedModel):
    order_id = models.UUIDField("Заказ", null=True, blank=True)
    operation_id = models.UUIDField("Операция", null=True, blank=True)
    kind = models.CharField("Вид", max_length=8, choices=LineKind.choices)
    category = models.CharField("Категория", max_length=16, choices=LineCategory.choices)
    name = models.CharField("Наименование", max_length=255)
    quantity = models.DecimalField("Количество", max_digits=12, decimal_places=3)
    unit = models.CharField("Ед. изм.", max_length=16, default="шт")
    price = MoneyField(verbose_name="Цена", default=Decimal("0"))
    need_date = models.DateField("Нужно к")
    status = FSMField(
        "Статус",
        max_length=16,
        choices=LineStatus.choices,
        default=LineStatus.DRAFT,
        protected=True,
    )
    requisition_no = models.CharField("Заявка на закупку", max_length=32, blank=True)
    # Кто и когда передал в закупку — «Создал» и «Дата» реестра заявок (`renderProc`):
    # заявку оформляет не обязательно тот, кто завёл черновик.
    sent_at = models.DateTimeField("Передано в закупку", null=True, blank=True)
    sent_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Передал в закупку",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lines",
        verbose_name="Поставщик",
    )
    po_number = models.CharField("Заказ поставщику", max_length=64, blank=True)
    eta = models.DateField("Срок поставки", null=True, blank=True)
    received_at = models.DateField("Принято на склад", null=True, blank=True)
    received_qty = models.DecimalField(
        "Принято, кол-во", max_digits=12, decimal_places=3, null=True, blank=True
    )
    storage_place = models.CharField("Место хранения", max_length=128, blank=True)
    issued_at = models.DateField("Передано в производство", null=True, blank=True)
    issued_to = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Получил",
    )
    created_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Запросил",
        help_text="Пусто — создано системой по запуску заказа",
    )

    class Meta:
        verbose_name = "Строка потребности"
        verbose_name_plural = "Строки потребности"
        ordering = ["need_date", "created_at"]
        indexes = [
            models.Index(fields=["order_id", "kind"], name="supply_line_order_kind"),
            models.Index(fields=["operation_id"], name="supply_line_operation"),
            models.Index(fields=["status"], name="supply_line_status"),
            models.Index(fields=["requisition_no"], name="supply_line_requisition"),
        ]
        constraints = [
            models.CheckConstraint(
                name="supply_line_quantity_positive",
                condition=Q(quantity__gt=0, price__gte=0),
                violation_error_message="Количество больше нуля, цена не отрицательная.",
            ),
            models.CheckConstraint(
                name="supply_line_kind_matches_category",
                condition=(
                    Q(kind=LineKind.MATERIAL, category=LineCategory.MATERIAL)
                    | (Q(kind=LineKind.TOOL) & ~Q(category=LineCategory.MATERIAL))
                ),
                violation_error_message="Материал — вид «материалы», остальное — «оснастка».",
            ),
            models.CheckConstraint(
                name="supply_line_operation_needs_order",
                condition=Q(operation_id__isnull=True) | Q(order_id__isnull=False),
                violation_error_message="Операция указывается только у строки заказа.",
            ),
            models.CheckConstraint(
                name="supply_line_requisition_after_draft",
                condition=(
                    Q(status=LineStatus.DRAFT) | Q(sent_at__isnull=False) & ~Q(requisition_no="")
                ),
                violation_error_message="Переданная в закупку строка имеет номер и дату заявки.",
            ),
            models.CheckConstraint(
                name="supply_line_ordered_has_supplier",
                condition=(
                    ~Q(status=LineStatus.ORDERED)
                    | Q(supplier__isnull=False, eta__isnull=False) & ~Q(po_number="")
                ),
                violation_error_message="Заказанная строка — с поставщиком, номером и сроком.",
            ),
            models.CheckConstraint(
                name="supply_line_received_has_receipt",
                condition=(
                    ~Q(status=LineStatus.RECEIVED)
                    | Q(received_at__isnull=False, received_qty__isnull=False)
                ),
                violation_error_message="Принятая строка — с датой и количеством приёмки.",
            ),
            models.CheckConstraint(
                name="supply_line_reserved_has_date",
                condition=~Q(status=LineStatus.RESERVED) | Q(received_at__isnull=False),
                violation_error_message="Резерв со склада — с датой резерва.",
            ),
            models.CheckConstraint(
                name="supply_line_issued_has_recipient",
                condition=(
                    ~Q(status=LineStatus.ISSUED)
                    | Q(issued_at__isnull=False, issued_to__isnull=False)
                ),
                violation_error_message="Переданная в производство строка — с датой и получателем.",
            ),
            models.CheckConstraint(
                name="supply_line_received_qty_non_negative",
                condition=Q(received_qty__isnull=True) | Q(received_qty__gte=0),
                violation_error_message="Принятое количество не может быть отрицательным.",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @transition(field=status, source=LineStatus.DRAFT, target=LineStatus.SENT)
    def mark_sent(self) -> None:
        pass

    @transition(field=status, source=LineStatus.SENT, target=LineStatus.ORDERED)
    def mark_ordered(self) -> None:
        pass

    @transition(field=status, source=LineStatus.ORDERED, target=LineStatus.RECEIVED)
    def mark_received(self) -> None:
        pass

    @transition(field=status, source=LineStatus.SENT, target=LineStatus.RESERVED)
    def mark_reserved(self) -> None:
        pass

    @transition(
        field=status,
        source=[LineStatus.RECEIVED, LineStatus.RESERVED],
        target=LineStatus.ISSUED,
    )
    def mark_issued(self) -> None:
        pass


class PurchaseLineHistory(UUIDPrimaryKeyModel):
    """История строки «кто, когда, что» (`PurchaseLineEvent` спецификации; имя
    `PurchaseLineEvent` занято событийной моделью pghistory для `PurchaseLine`). Нужна
    экрану: pghistory хранит изменения полей, но не текст действия («Заказано у …,
    срок …»). Сама история не отслеживается — она и есть история."""

    line = models.ForeignKey(
        PurchaseLine, on_delete=models.CASCADE, related_name="history", verbose_name="Строка"
    )
    author = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Автор",
        help_text="Пусто — система",
    )
    text = models.TextField("Текст")
    # Не auto_now_add: демо-данные пишут историю задним числом.
    created_at = models.DateTimeField("Дата", default=timezone.now)

    class Meta:
        verbose_name = "Событие строки потребности"
        verbose_name_plural = "История строк потребности"
        ordering = ["line", "created_at"]

    def __str__(self) -> str:
        return self.text[:60]
