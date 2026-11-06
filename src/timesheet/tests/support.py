"""Общие помощники тестов табеля."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

from src.core.events.base import DomainEvent
from src.core.org.models import Department, Employee
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory
from src.timesheet.calculations import is_weekend, month_days
from src.timesheet.models import TimeCode, WorkAllocation, WorkerProfile
from src.timesheet.tests.factories import WorkerProfileFactory

# Сентябрь 2026: 22 рабочих дня, всегда в прошлом относительно прогона тестов.
SEPTEMBER = date(2026, 9, 1)
OCTOBER = date(2026, 10, 1)
TODAY = date(2026, 11, 6)


@dataclasses.dataclass(frozen=True)
class RepairClosedForTest(DomainEvent):
    """Событие `equipment.repair_closed` v1 — своё в тестах: модуль `equipment` пишет
    другая команда, и его `events.py` в этой ветке пуст."""

    event_type: ClassVar[str] = "equipment.repair_closed"
    version: ClassVar[int] = 1

    date: date
    number: str
    workers: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["equipment_id"] = str(self.aggregate_id)
        return payload


def worker(
    department: Department | None = None,
    *,
    work_center_id: Any = None,
    rate: str = "1000",
    **employee: Any,
) -> WorkerProfile:
    department = department or DepartmentFactory.create()
    profile: WorkerProfile = WorkerProfileFactory.create(
        employee=EmployeeFactory.create(department=department, **employee),
        work_center_id=work_center_id,
        hourly_rate=Decimal(rate),
    )
    return profile


def fill_month(employee: Employee, month: date, *, skip: tuple[int, ...] = ()) -> None:
    """8 ч накладных каждый будний день месяца, кроме дней `skip`."""

    code = TimeCode.objects.get(code="Я")
    WorkAllocation.objects.bulk_create(
        [
            WorkAllocation(
                employee=employee, date=d, time_code=code, target="overhead", hours=Decimal("8")
            )
            for d in month_days(month)
            if not is_weekend(d) and d.day not in skip
        ]
    )
