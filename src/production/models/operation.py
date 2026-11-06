"""Операция заказа, связь операций и освоение (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.1, «Операции»).

Виза операции — статусный переход с отметкой, а не маршрут согласования (§2.3).
`planned_start` хранится и пересчитывается сервисом `reschedule` при любой правке
графика: операцию двигают мышью, перенос записывается как `not_before`, а дата начала —
результат пересчёта (`docs/adr/0034-khranimye-daty-operatsiy.md`).

Что обе операции связи принадлежат одному заказу, проверяет триггер миграции
`0003_operation_dependency_same_order`; отсутствие циклов — сервис.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_fsm import FSMField, transition

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import OperationStatus
from .order import ProductionOrder
from .reference import WorkCenter

PROGRESS_STEPS = tuple(range(0, 101, 10))


@track()
class Operation(UUIDPrimaryKeyModel, TimeStampedModel):
    order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name="operations",
        verbose_name="Заказ",
    )
    seq = models.PositiveSmallIntegerField("Номер")
    name = models.CharField("Наименование", max_length=255)
    work_center = models.ForeignKey(
        WorkCenter,
        on_delete=models.PROTECT,
        related_name="operations",
        verbose_name="Участок",
    )
    hours = models.DecimalField(
        "Трудоёмкость, н-ч (снабжение — дни)", max_digits=10, decimal_places=2
    )
    people = models.PositiveSmallIntegerField("Исполнителей", default=1)
    responsible = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="production_operations",
        verbose_name="Ответственный",
    )
    not_before = models.DateField("Не ранее", null=True, blank=True)
    planned_start = models.DateField("Плановое начало", null=True, blank=True)
    status = FSMField(
        "Статус",
        max_length=16,
        choices=OperationStatus.choices,
        default=OperationStatus.WAIT,
        protected=True,
    )
    progress = models.PositiveSmallIntegerField("Выполнено, %", default=0)
    started_at = models.DateTimeField("Начата", null=True, blank=True)
    started_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Начал",
        help_text="Пусто — начата системой (автостарт)",
    )
    approved_at = models.DateTimeField("Дата визы", null=True, blank=True)
    approved_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Завизировал",
    )
    approved_for = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Виза за",
        help_text="Если визу поставил начальник производства за ответственного",
    )

    class Meta:
        verbose_name = "Операция"
        verbose_name_plural = "Операции"
        ordering = ["order", "seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "seq"],
                name="production_operation_unique_seq",
                violation_error_message="Операция с таким номером в заказе уже есть.",
            ),
            models.CheckConstraint(
                name="production_operation_hours_non_negative",
                condition=Q(hours__gte=0),
                violation_error_message="Трудоёмкость не может быть отрицательной.",
            ),
            models.CheckConstraint(
                name="production_operation_people",
                condition=Q(people__gte=1),
                violation_error_message="Исполнителей — не меньше одного.",
            ),
            models.CheckConstraint(
                name="production_operation_progress_step",
                condition=Q(progress__in=PROGRESS_STEPS),
                violation_error_message="Выполнение — от 0 до 100 % с шагом 10.",
            ),
            models.CheckConstraint(
                name="production_operation_wait_is_clean",
                condition=(
                    ~Q(status=OperationStatus.WAIT)
                    | Q(progress=0, started_at__isnull=True, started_by__isnull=True)
                ),
                violation_error_message="Ожидающая операция не начата и не выполнена.",
            ),
            models.CheckConstraint(
                name="production_operation_started_attribution",
                condition=Q(status=OperationStatus.WAIT) | Q(started_at__isnull=False),
                violation_error_message="Начатая операция обязана иметь отметку о начале.",
            ),
            models.CheckConstraint(
                name="production_operation_check_full",
                condition=~Q(status=OperationStatus.CHECK) | Q(progress=100),
                violation_error_message="На визу передаётся только выполненная на 100 % операция.",
            ),
            models.CheckConstraint(
                name="production_operation_visa_iff_done",
                condition=(
                    Q(
                        status=OperationStatus.DONE,
                        progress=100,
                        approved_at__isnull=False,
                        approved_by__isnull=False,
                    )
                    | (
                        ~Q(status=OperationStatus.DONE)
                        & Q(
                            approved_at__isnull=True,
                            approved_by__isnull=True,
                            approved_for__isnull=True,
                        )
                    )
                ),
                violation_error_message="Виза есть ровно у выполненной операции.",
            ),
        ]
        indexes = [
            models.Index(
                fields=["responsible", "status"],
                condition=~Q(status=OperationStatus.DONE),
                name="production_operation_my_open",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.seq} {self.name}"

    @transition(field=status, source=OperationStatus.WAIT, target=OperationStatus.WORK)
    def mark_started(self) -> None:
        pass

    @transition(field=status, source=OperationStatus.WORK, target=OperationStatus.CHECK)
    def mark_submitted(self) -> None:
        pass

    @transition(field=status, source=OperationStatus.CHECK, target=OperationStatus.WORK)
    def mark_returned(self) -> None:
        pass

    @transition(
        field=status,
        source=[OperationStatus.WORK, OperationStatus.CHECK],
        target=OperationStatus.DONE,
    )
    def mark_approved(self) -> None:
        pass

    @transition(
        field=status,
        source=[OperationStatus.WORK, OperationStatus.CHECK],
        target=OperationStatus.WAIT,
    )
    def mark_reset(self) -> None:
        pass


@track()
class OperationDependency(UUIDPrimaryKeyModel, TimeStampedModel):
    """Связь «окончание → начало» без задержки (в прототипе её нет)."""

    predecessor = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name="successor_links",
        verbose_name="Предшественник",
    )
    successor = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name="predecessor_links",
        verbose_name="Последователь",
    )

    class Meta:
        verbose_name = "Связь операций"
        verbose_name_plural = "Связи операций"
        constraints = [
            models.CheckConstraint(
                name="production_dependency_not_self",
                condition=~Q(predecessor=models.F("successor")),
                violation_error_message="Операция не может зависеть от самой себя.",
            ),
            models.UniqueConstraint(
                fields=["predecessor", "successor"],
                name="production_dependency_unique_pair",
                violation_error_message="Такая связь уже есть.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.predecessor_id} → {self.successor_id}"


class OperationEarning(UUIDPrimaryKeyModel):
    """Освоение — журнал приращений нормо-часов (`earnOp` прототипа). Сумма по операции
    равна `hours × progress / 100`; откат прогресса пишется отрицательной строкой, а не
    правкой старых — освоение прошлых недель уже попало в отсечки. Сам журнал не
    отслеживается pghistory: он и есть история."""

    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        related_name="earnings",
        verbose_name="Операция",
    )
    date = models.DateField("Дата")
    hours = models.DecimalField("Нормо-часы", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField("Дата записи", default=timezone.now)

    class Meta:
        verbose_name = "Освоение"
        verbose_name_plural = "Освоение"
        ordering = ["operation", "date", "created_at"]
        indexes = [models.Index(fields=["date"], name="production_earning_date")]
        constraints = [
            models.CheckConstraint(
                name="production_earning_not_zero",
                condition=~Q(hours=0),
                violation_error_message="Нулевое освоение не записывается.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operation_id} {self.date}: {self.hours}"
