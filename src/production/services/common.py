"""Общие куски сервисов «Производства»: блокировка заказа, журнал, освоение, пересчёт
графика. Вызываются только внутри транзакции вызывающего сервиса."""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db.models import Sum
from django.utils import timezone

from src.core.common.scheduling import forward_pass
from src.core.org import facade as org
from src.core.org.models import Employee
from src.production.exceptions import EmployeeNotFound
from src.production.models import (
    JournalKind,
    Operation,
    OperationDependency,
    OperationEarning,
    OrderJournalEntry,
    OrderStage,
    ProductionOrder,
)
from src.production.planning import network

_HUNDRED = Decimal(100)
_HOURS_QUANT = Decimal("0.01")


def lock_order(order_id: UUID) -> ProductionOrder:
    """Заказ под `select_for_update` — точка сериализации правок графика, статусов и
    связей: две параллельные вставки связей не замкнут цикл вдвоём."""

    return ProductionOrder.objects.select_for_update().get(id=order_id)


def lock_operation(operation_id: UUID) -> tuple[ProductionOrder, Operation]:
    order_id = Operation.objects.values_list("order_id", flat=True).get(id=operation_id)
    order = lock_order(order_id)
    operation = (
        Operation.objects.select_for_update(of=("self",))
        .select_related("work_center")
        .get(id=operation_id)
    )
    return order, operation


def get_employee(employee_id: UUID) -> Employee | None:
    return Employee.objects.filter(id=employee_id).first()


def ensure_active_employee(employee_id: UUID | None) -> None:
    if employee_id is None:
        return
    if employee_id not in {brief.id for brief in org.list_active_employees()}:
        raise EmployeeNotFound


def journal(
    order: ProductionOrder,
    kind: JournalKind,
    text: str,
    *,
    operation: Operation | None = None,
    author_id: UUID | None = None,
    stage: str = "",
    at: datetime | None = None,
) -> OrderJournalEntry:
    return OrderJournalEntry.objects.create(
        order=order,
        operation=operation,
        stage=stage if stage or operation is not None else order.stage,
        kind=kind,
        author_id=author_id,
        text=text,
        created_at=at if at is not None else timezone.now(),
    )


def earned_hours(operation: Operation) -> Decimal:
    total = OperationEarning.objects.filter(operation=operation).aggregate(total=Sum("hours"))[
        "total"
    ]
    return total if total is not None else Decimal("0")


def earn_to(operation: Operation, progress: int, *, day: date | None = None) -> None:
    """Освоение до `hours × progress / 100` одной строкой-приращением (`earnOp`
    прототипа). Приращение считается от уже записанной суммы, а не от прошлого
    процента: так сумма по операции равна округлённой цели без накопления копеек.
    Снабжение часов не осваивает."""

    if operation.work_center.is_supply:
        return
    target = (operation.hours * progress / _HUNDRED).quantize(_HOURS_QUANT, ROUND_HALF_UP)
    delta = target - earned_hours(operation)
    if delta:
        OperationEarning.objects.create(
            operation=operation, date=day or timezone.localdate(), hours=delta
        )


def reschedule(order: ProductionOrder, *, clamp_today: bool = True) -> None:
    """Пересчёт хранимых `planned_start` прямым проходом (§2.1). У отгруженного заказа
    план заморожен. «Не раньше сегодня» — для заказа в работе; при создании заказа
    не применяется (`launchDialog` прототипа)."""

    if order.stage == OrderStage.DONE:
        return
    operations = list(Operation.objects.filter(order=order).select_related("work_center"))
    if not operations:
        return
    dependencies = list(OperationDependency.objects.filter(successor__order=order))
    nodes, edges = network(operations, dependencies)
    starts = forward_pass(
        nodes,
        edges,
        base=order.planned_start,
        not_earlier_than=timezone.localdate() if clamp_today else None,
    )
    changed = []
    for op in operations:
        if op.planned_start != starts[op.id]:
            op.planned_start = starts[op.id]
            changed.append(op)
    if changed:
        Operation.objects.bulk_update(changed, ["planned_start"])


def fmt_date(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day is not None else "—"


__all__ = [
    "earn_to",
    "earned_hours",
    "ensure_active_employee",
    "fmt_date",
    "get_employee",
    "journal",
    "lock_operation",
    "lock_order",
    "reschedule",
]
