"""Публичный интерфейс модуля «Производство» для других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, «Фасад»).

Наружу — только датаклассы этого файла и UUID: модели модуля чужим модулям не
отдаются (И1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.production import selectors
from src.production.models import (
    JournalKind,
    Operation,
    OperationStatus,
    ProductionOrder,
    ProductTemplate,
    WorkCenter,
)
from src.production.planning import finish_of
from src.production.services import demo as demo_services
from src.production.services import journal as journal_services
from src.production.services.order import LaunchData, LaunchOperation
from src.production.services.order import create_order_from_inquiry as _create_order

__all__ = [
    "EarningRow",
    "JournalKind",
    "LaunchData",
    "LaunchOperation",
    "OperationBrief",
    "OrderBrief",
    "TemplateBrief",
    "TemplateMaterialBrief",
    "TemplateOperationBrief",
    "WorkCenterBrief",
    "add_journal_entry",
    "create_order_from_inquiry",
    "get_operations_brief",
    "get_orders_brief",
    "get_template",
    "get_work_center",
    "list_active_orders",
    "list_earnings",
    "list_order_operations",
    "list_planned_operations",
    "list_work_centers",
    "order_has_kd",
    "seed_demo",
]


@dataclass(frozen=True)
class WorkCenterBrief:
    id: UUID
    code: str
    short_name: str
    name: str
    rate: Decimal
    capacity: int
    phase: str
    is_supply: bool
    responsible_id: UUID | None


@dataclass(frozen=True)
class TemplateMaterialBrief:
    name: str
    qty_per_unit: Decimal
    price: Decimal


@dataclass(frozen=True)
class TemplateOperationBrief:
    seq: int
    name: str
    work_center_id: UUID
    hours: Decimal
    scales_with_qty: bool
    people: int
    # Индексы предшественников в списке `TemplateBrief.operations`.
    predecessor_indexes: tuple[int, ...]


@dataclass(frozen=True)
class TemplateBrief:
    id: UUID
    code: str
    name: str
    is_active: bool
    materials: list[TemplateMaterialBrief]
    operations: list[TemplateOperationBrief]


@dataclass(frozen=True)
class OrderBrief:
    id: UUID
    number: str
    inquiry_id: UUID | None
    product_name: str
    customer_name: str
    quantity: Decimal
    stage: str
    manager_id: UUID
    planned_start: date
    due_date: date
    planned_finish: date | None
    contract_total: Decimal
    shipped_at: date | None


@dataclass(frozen=True)
class OperationBrief:
    id: UUID
    order_id: UUID
    seq: int
    name: str
    work_center_id: UUID
    status: str
    progress: int
    responsible_id: UUID | None
    planned_start: date | None
    planned_finish: date | None
    hours: Decimal
    people: int
    is_supply: bool


@dataclass(frozen=True)
class EarningRow:
    operation_id: UUID
    order_id: UUID
    work_center_id: UUID
    date: date
    hours: Decimal


def _work_center_brief(center: WorkCenter) -> WorkCenterBrief:
    return WorkCenterBrief(
        id=center.id,
        code=center.code,
        short_name=center.short_name,
        name=center.name,
        rate=center.hourly_rate,
        capacity=center.capacity,
        phase=center.phase,
        is_supply=center.is_supply,
        responsible_id=center.responsible_id,
    )


def list_work_centers() -> list[WorkCenterBrief]:
    return [_work_center_brief(center) for center in selectors.list_work_centers()]


def get_work_center(work_center_id: UUID) -> WorkCenterBrief | None:
    center = selectors.get_work_center(work_center_id)
    return _work_center_brief(center) if center is not None else None


def _template_brief(template: ProductTemplate) -> TemplateBrief:
    operations = sorted(template.operations.all(), key=lambda op: (op.sort_order, op.seq))
    index = {op.id: i for i, op in enumerate(operations)}
    materials = sorted(template.materials.all(), key=lambda m: m.sort_order)
    return TemplateBrief(
        id=template.id,
        code=template.code,
        name=template.name,
        is_active=template.is_active,
        materials=[
            TemplateMaterialBrief(name=m.name, qty_per_unit=m.qty_per_unit, price=m.price)
            for m in materials
        ],
        operations=[
            TemplateOperationBrief(
                seq=op.seq,
                name=op.name,
                work_center_id=op.work_center_id,
                hours=op.hours,
                scales_with_qty=op.scales_with_qty,
                people=op.people,
                predecessor_indexes=tuple(
                    sorted(index[link.predecessor_id] for link in op.predecessor_links.all())
                ),
            )
            for op in operations
        ],
    )


def get_template(code_or_id: str | UUID) -> TemplateBrief | None:
    template = selectors.get_template(code_or_id)
    return _template_brief(template) if template is not None else None


def create_order_from_inquiry(data: LaunchData, *, actor_id: UUID) -> UUID:
    """Вызывается `sales.launch_inquiry` внутри её транзакции."""

    return _create_order(data, actor_id=actor_id)


def _order_brief(order: ProductionOrder) -> OrderBrief:
    finishes = [finish_of(op) for op in order.operations.all()]
    return OrderBrief(
        id=order.id,
        number=order.number,
        inquiry_id=order.inquiry_id,
        product_name=order.product_name,
        customer_name=order.customer_name,
        quantity=order.quantity,
        stage=order.stage,
        manager_id=order.manager_id,
        planned_start=order.planned_start,
        due_date=order.due_date,
        planned_finish=max((f for f in finishes if f is not None), default=None),
        contract_total=order.contract_total,
        shipped_at=order.shipped_at.date() if order.shipped_at else None,
    )


def get_orders_brief(ids: Iterable[UUID]) -> dict[UUID, OrderBrief]:
    return {
        order.id: _order_brief(order)
        for order in selectors.list_orders_with_operations(ids=list(ids))
    }


def list_active_orders() -> list[OrderBrief]:
    """Заказы, кроме отгруженных."""

    return [_order_brief(o) for o in selectors.list_orders_with_operations(active_only=True)]


def _operation_brief(op: Operation) -> OperationBrief:
    return OperationBrief(
        id=op.id,
        order_id=op.order_id,
        seq=op.seq,
        name=op.name,
        work_center_id=op.work_center_id,
        status=op.status,
        progress=op.progress,
        responsible_id=op.responsible_id,
        planned_start=op.planned_start,
        planned_finish=finish_of(op),
        hours=op.hours,
        people=op.people,
        is_supply=op.work_center.is_supply,
    )


def get_operations_brief(ids: Iterable[UUID]) -> dict[UUID, OperationBrief]:
    return {op.id: _operation_brief(op) for op in selectors.list_operations(ids=list(ids))}


def list_order_operations(order_id: UUID) -> list[OperationBrief]:
    return [_operation_brief(op) for op in selectors.list_operations(order_id=order_id)]


def list_planned_operations(work_center_id: UUID, day: date) -> list[OperationBrief]:
    """Не выполненные операции участка, чей план покрывает `day` — «заполнить по плану»
    в табеле."""

    result = []
    for op in selectors.list_operations(work_center_id=work_center_id, active_orders_only=True):
        finish = finish_of(op)
        if (
            op.status != OperationStatus.DONE
            and op.planned_start is not None
            and finish is not None
            and op.planned_start <= day <= finish
        ):
            result.append(_operation_brief(op))
    return result


def list_earnings(date_from: date, date_to: date) -> list[EarningRow]:
    return [
        EarningRow(
            operation_id=row.operation_id,
            order_id=order_id,
            work_center_id=work_center_id,
            date=row.date,
            hours=row.hours,
        )
        for row, order_id, work_center_id in selectors.list_earnings(date_from, date_to)
    ]


def add_journal_entry(
    order_id: UUID,
    kind: str,
    text: str,
    *,
    operation_id: UUID | None = None,
    author_employee_id: UUID | None = None,
) -> None:
    """Запись в журнал заказа от другого модуля (`quality` — `qc`, `supply` — `proc`)
    синхронно, в транзакции вызывающего."""

    journal_services.add_journal_entry(
        order_id,
        JournalKind(kind),
        text,
        operation_id=operation_id,
        author_employee_id=author_employee_id,
    )


def order_has_kd(order_id: UUID) -> bool:
    return selectors.order_has_kd(order_id)


def seed_demo() -> None:
    """Демо-данные производства: участки, шаблоны, настройки ответственных и заказы
    прототипа. Сотрудники должны уже существовать (команда `seed_demo`)."""

    demo_services.seed_demo()
