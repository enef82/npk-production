"""Фасад табеля для других модулей: разноска со ставками, отработанные часы участков,
факт трудозатрат заказа (точные суммы в `Decimal`), демо-данные."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory
from src.timesheet import facade
from src.timesheet.models import (
    AllocationTarget,
    PeriodStatus,
    TimeCode,
    TimesheetPeriod,
    WorkAllocation,
    WorkerProfile,
)
from src.timesheet.services.demo import name_key, seed_demo
from src.timesheet.tests.factories import WorkAllocationFactory
from src.timesheet.tests.support import TODAY, worker

pytestmark = pytest.mark.django_db

DAY = date(2026, 9, 1)


def _code(code: str) -> TimeCode:
    return TimeCode.objects.get(code=code)


def test_факт_по_заказу_часы_и_стоимость_с_коэффициентами_кодов() -> None:
    order, other_order = uuid4(), uuid4()
    a = worker(rate="1000")
    b = worker(rate="1200")
    WorkAllocationFactory.create(employee=a.employee, target="order", order_id=order)
    WorkAllocationFactory.create(
        employee=a.employee,
        target="order",
        order_id=order,
        time_code=_code("С"),
        hours=Decimal("2"),
    )
    WorkAllocationFactory.create(
        employee=b.employee,
        target="order",
        order_id=order,
        time_code=_code("РВ"),
        hours=Decimal("4"),
    )
    WorkAllocationFactory.create(employee=b.employee, target="order", order_id=other_order)

    actual = facade.actual_by_order([order])

    # 8 × 1000 + 2 × 1000 × 1,5 + 4 × 1200 × 2 = 8000 + 3000 + 9600
    assert actual == {order: facade.OrderActual(hours=Decimal("14.00"), cost=Decimal("20600"))}


def test_отработанные_часы_по_участкам_без_отсутствий_и_без_участка() -> None:
    wc = uuid4()
    a = worker(work_center_id=wc)
    b = worker(work_center_id=wc)
    office = worker()
    WorkAllocationFactory.create(employee=a.employee, date=DAY)
    WorkAllocationFactory.create(employee=b.employee, date=DAY, hours=Decimal("6.5"))
    WorkAllocationFactory.create(
        employee=b.employee, date=date(2026, 9, 2), target="", time_code=_code("Б")
    )
    WorkAllocationFactory.create(employee=office.employee, date=DAY)
    WorkAllocationFactory.create(employee=a.employee, date=date(2026, 10, 1))

    assert facade.worked_hours_by_work_center(DAY, date(2026, 9, 30)) == {wc: Decimal("14.50")}


def test_строки_разноски_несут_код_коэффициент_участок_и_ставку() -> None:
    wc, order, operation = uuid4(), uuid4(), uuid4()
    profile = worker(work_center_id=wc, rate="1300")
    WorkAllocationFactory.create(
        employee=profile.employee,
        target="order",
        order_id=order,
        operation_id=operation,
        time_code=_code("С"),
        hours=Decimal("2"),
    )

    assert facade.list_allocations(DAY, DAY) == [
        facade.AllocationRow(
            employee_id=profile.employee_id,
            date=DAY,
            code="С",
            is_work=True,
            cost_multiplier=Decimal("1.50"),
            target=AllocationTarget.ORDER,
            order_id=order,
            operation_id=operation,
            hours=Decimal("2.00"),
            work_center_id=wc,
            hourly_rate=Decimal("1300.0000"),
        )
    ]


def test_ставки_и_профили_работников() -> None:
    profile = worker(rate="1450.50")
    without = EmployeeFactory.create()

    assert facade.get_hourly_rates([profile.employee_id, without.id]) == {
        profile.employee_id: Decimal("1450.5000")
    }
    briefs = facade.get_worker_profiles()
    assert [(b.employee_id, b.personnel_no) for b in briefs] == [
        (profile.employee_id, profile.employee.personnel_number)
    ]


def test_ключ_фио_одинаков_для_краткой_и_полной_формы() -> None:
    assert name_key("Белов С.А.") == name_key("Белов Сергей Александрович") == "белов|са"


def test_демо_без_сотрудников_ничего_не_создаёт() -> None:
    assert facade.seed_demo() == 0
    assert not WorkerProfile.objects.exists()


def test_демо_создаёт_профили_и_разноску_найденным_сотрудникам() -> None:
    okb = DepartmentFactory.create(code="OKB")
    sbm = DepartmentFactory.create(code="SMU", legal_entity=okb.legal_entity)
    belov = EmployeeFactory.create(full_name="Белов Сергей Александрович", department=okb)
    komarov = EmployeeFactory.create(full_name="Комаров В.В.", department=sbm)
    EmployeeFactory.create(full_name="Посторонний П.П.", department=sbm)
    em = uuid4()
    order, operation = uuid4(), uuid4()

    created = seed_demo([(order, operation, em)], work_centers={"em": em}, today=TODAY)

    assert created > 0
    profiles = {p.employee_id: p for p in WorkerProfile.objects.all()}
    assert set(profiles) == {belov.id, komarov.id}
    assert (profiles[komarov.id].work_center_id, profiles[komarov.id].hourly_rate) == (
        em,
        Decimal("1200.0000"),
    )
    assert WorkAllocation.objects.filter(employee=komarov, order_id=order).exists()
    assert not WorkAllocation.objects.filter(employee=belov, order_id__isnull=False).exists()
    assert not WorkAllocation.objects.filter(date__gte=TODAY, time_code__code="Я").exists()
    # Сверхурочные электромонтажника за 3 и 2 дня до сегодня.
    assert WorkAllocation.objects.filter(employee=komarov, time_code__code="С").count() == 2
    statuses = dict(
        TimesheetPeriod.objects.filter(month=date(2026, 10, 1)).values_list(
            "department__code", "status"
        )
    )
    assert statuses == {"OKB": PeriodStatus.APPROVED, "SMU": PeriodStatus.ON_REVIEW}

    assert seed_demo([(order, operation, em)], work_centers={"em": em}, today=TODAY) == 0
    assert WorkAllocation.objects.count() == created
