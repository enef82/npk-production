"""Единственная точка, где «Табель» узнаёт о заказах и операциях модуля `production`
(`docs/adr/0033-timesheet-tabelnyy-nomer-i-svyaz-s-production.md`): плановые операции
для «заполнить по плану», менеджеры заказов для виз периода, номера заказов для
аналитики пакетов 1С."""

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
