"""Ограничения БД модуля «Табель»: попытка нарушить → `IntegrityError` (CLAUDE.md §8)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from src.core.org.tests.factories import EmployeeFactory
from src.timesheet.models import (
    AllocationSource,
    PeriodEventKind,
    TimeCode,
    TimesheetPeriod,
    TimesheetPeriodEvent,
)
from src.timesheet.tests.factories import (
    TimesheetPeriodFactory,
    WorkAllocationFactory,
    WorkerProfileFactory,
)
from src.timesheet.tests.reference_data import TIME_CODES

pytestmark = pytest.mark.django_db


def test_миграция_засевает_десять_кодов_прототипа() -> None:
    """Доказательно при `pytest --create-db`: на `--reuse-db` коды могла восстановить
    фикстура `conftest._time_codes` из того же списка."""

    actual = {
        (c.code, c.name, c.is_work, c.is_allocatable, c.cost_multiplier)
        for c in TimeCode.objects.all()
    }
    assert actual == set(TIME_CODES)


@pytest.mark.parametrize("hours", [Decimal("0"), Decimal("-1"), Decimal("24.5")])
def test_часы_строки_вне_диапазона_нарушают_constraint(hours: Decimal) -> None:
    with pytest.raises(IntegrityError):
        WorkAllocationFactory.create(hours=hours)


def test_строка_на_заказ_без_заказа_невозможна() -> None:
    with pytest.raises(IntegrityError):
        WorkAllocationFactory.create(target="order", order_id=None)


def test_заказ_у_строки_накладных_невозможен() -> None:
    with pytest.raises(IntegrityError):
        WorkAllocationFactory.create(target="overhead", order_id=uuid4())


def test_операция_без_заказа_невозможна() -> None:
    with pytest.raises(IntegrityError):
        WorkAllocationFactory.create(target="overhead", operation_id=uuid4())


def test_разноска_из_ремонта_без_номера_невозможна() -> None:
    with pytest.raises(IntegrityError):
        WorkAllocationFactory.create(target="repair", source=AllocationSource.REPAIR)


def test_один_ремонт_у_сотрудника_разносится_один_раз() -> None:
    employee = EmployeeFactory.create()
    kwargs = {
        "employee": employee,
        "target": "repair",
        "source": AllocationSource.REPAIR,
        "source_ref": "АР-0001",
    }
    WorkAllocationFactory.create(**kwargs)
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkAllocationFactory.create(**kwargs, date=date(2026, 9, 2))


def test_табель_подразделения_за_месяц_один() -> None:
    period = TimesheetPeriodFactory.create()
    with pytest.raises(IntegrityError):
        TimesheetPeriodFactory.create(department=period.department, month=period.month)


def test_месяц_табеля_только_первым_числом() -> None:
    with pytest.raises(IntegrityError):
        TimesheetPeriodFactory.create(month=date(2026, 9, 2))


def test_версия_табеля_не_меньше_единицы() -> None:
    period = TimesheetPeriodFactory.create()
    with pytest.raises(IntegrityError):
        TimesheetPeriod.objects.filter(id=period.id).update(version=0)


def test_возврат_табеля_без_причины_невозможен() -> None:
    period = TimesheetPeriodFactory.create()
    with pytest.raises(IntegrityError):
        TimesheetPeriodEvent.objects.create(period=period, kind=PeriodEventKind.RETURNED, version=1)


def test_виза_менеджера_без_менеджера_невозможна() -> None:
    period = TimesheetPeriodFactory.create()
    with pytest.raises(IntegrityError):
        TimesheetPeriodEvent.objects.create(
            period=period, kind=PeriodEventKind.MANAGER_CONFIRMED, version=1
        )


def test_менеджер_у_не_визы_невозможен() -> None:
    period = TimesheetPeriodFactory.create()
    with pytest.raises(IntegrityError):
        TimesheetPeriodEvent.objects.create(
            period=period,
            kind=PeriodEventKind.SUBMITTED,
            version=1,
            manager=EmployeeFactory.create(),
        )


def test_отпуск_не_может_разноситься_на_объекты() -> None:
    with pytest.raises(IntegrityError):
        TimeCode.objects.create(code="X", name="X", is_work=False, is_allocatable=True)


def test_нулевой_коэффициент_кода_невозможен() -> None:
    with pytest.raises(IntegrityError):
        TimeCode.objects.create(code="X", name="X", cost_multiplier=Decimal("0"))


def test_отрицательная_ставка_работника_невозможна() -> None:
    with pytest.raises(IntegrityError):
        WorkerProfileFactory.create(hourly_rate=Decimal("-1"))
