"""Единственная точка, где «Табель» узнаёт о заказах и операциях модуля `production`
(`docs/adr/0033-timesheet-tabelnyy-nomer-i-svyaz-s-production.md`): плановые операции
для «заполнить по плану», менеджеры заказов для виз периода, номера заказов для
аналитики пакетов 1С, подписи заказов и операций для экрана."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from src.production import facade as production
from src.timesheet.calculations import PlannedOp


def planned_operations(work_center_id: UUID | None, day: date) -> list[PlannedOp]:
    if work_center_id is None:
        return []
    operations = production.list_planned_operations(work_center_id, day)
    orders = production.get_orders_brief({op.order_id for op in operations})
    return [
        PlannedOp(
            operation_id=op.id,
            order_id=op.order_id,
            label=f"{orders[op.order_id].number} · {op.seq}. {op.name}"
            if op.order_id in orders
            else f"{op.seq}. {op.name}",
        )
        for op in operations
    ]


def order_managers(order_ids: Iterable[UUID]) -> dict[UUID, UUID]:
    """Заказ → сотрудник-менеджер."""

    return {
        oid: brief.manager_id for oid, brief in production.get_orders_brief(set(order_ids)).items()
    }


def order_numbers(order_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Заказ → номер для аналитики 1С."""

    return {oid: brief.number for oid, brief in production.get_orders_brief(set(order_ids)).items()}


def _order_label(number: str, product_name: str) -> str:
    return f"{number} · {product_name}" if product_name else number


def order_labels(order_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Заказ → подпись для экрана «Табель» («номер · изделие»)."""

    return {
        oid: _order_label(brief.number, brief.product_name)
        for oid, brief in production.get_orders_brief(set(order_ids)).items()
    }


def operation_labels(operation_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Операция → подпись «№. название» для строк диалога дня."""

    return {
        oid: f"{op.seq}. {op.name}"
        for oid, op in production.get_operations_brief(set(operation_ids)).items()
    }


def order_options() -> list[tuple[UUID, str]]:
    """Заказы в работе — выбор объекта разноски в диалоге дня."""

    return [
        (brief.id, _order_label(brief.number, brief.product_name))
        for brief in production.list_active_orders()
    ]


def operation_options(order_id: UUID) -> list[tuple[UUID, str, UUID]]:
    """Операции заказа (кроме снабжения): id, подпись, участок."""

    return [
        (op.id, f"{op.seq}. {op.name}", op.work_center_id)
        for op in production.list_order_operations(order_id)
        if not op.is_supply
    ]
