"""Публичный интерфейс модуля «Табель» для других модулей (спецификация §3.5).

Потребители: `analytics` — выработка участков и сотрудников (`list_allocations`,
`worked_hours_by_work_center`), `production`/`analytics` — факт трудозатрат заказа
(`actual_by_order`), `equipment` — стоимость часов ремонта (`get_hourly_rates`),
команда `seed_demo`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.timesheet import selectors
from src.timesheet.models import AllocationTarget
from src.timesheet.selectors import AllocationRow, OrderActual
from src.timesheet.services import demo

__all__ = [
    "AllocationRow",
    "AllocationTarget",
    "OrderActual",
    "WorkerProfileBrief",
    "actual_by_order",
    "get_hourly_rates",
    "get_worker_profiles",
    "list_allocations",
    "seed_demo",
    "worked_hours_by_work_center",
]


@dataclass(frozen=True)
class WorkerProfileBrief:
    employee_id: UUID
    full_name: str
    personnel_no: str  # табельный номер — `core.org.Employee.personnel_number`
    department_id: UUID
    work_center_id: UUID | None
    hourly_rate: Decimal


def get_worker_profiles() -> list[WorkerProfileBrief]:
    return [
        WorkerProfileBrief(
            employee_id=p.employee_id,
            full_name=p.employee.full_name,
            personnel_no=p.employee.personnel_number,
            department_id=p.employee.department_id,
            work_center_id=p.work_center_id,
            hourly_rate=p.hourly_rate,
        )
        for p in selectors.list_worker_profiles()
    ]


def list_allocations(date_from: date, date_to: date) -> list[AllocationRow]:
    """Строки разноски за период с кодом, коэффициентом, участком и ставкой работника."""

    return selectors.list_allocation_rows(date_from, date_to)


def worked_hours_by_work_center(date_from: date, date_to: date) -> dict[UUID, Decimal]:
    return selectors.worked_hours_by_work_center(date_from, date_to)


def actual_by_order(order_ids: Iterable[UUID]) -> dict[UUID, OrderActual]:
    return selectors.actual_by_order(order_ids)


def get_hourly_rates(employee_ids: Iterable[UUID]) -> dict[UUID, Decimal]:
    """Ставка работника; сотрудника без профиля в ответе нет."""

    return selectors.hourly_rates(employee_ids)


def seed_demo(
    orders: Sequence[tuple[UUID, UUID, UUID]] = (),
    *,
    work_centers: Mapping[str, UUID] | None = None,
    plan_windows: Mapping[UUID, tuple[date, date]] | None = None,
) -> int:
    """`orders` — (заказ, операция, участок); `work_centers` — код участка прототипа →
    id; `plan_windows` — операция → плановые даты. Все три даёт `production`; без них
    разноска — накладные."""

    return demo.seed_demo(orders, work_centers=work_centers, plan_windows=plan_windows)
