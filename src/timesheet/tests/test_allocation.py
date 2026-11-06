"""Разноска: правка строк дня только в открытом периоде, лимит 24 ч в сумме за день,
«заполнить по плану» (`autoFillDay`)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.core.accounts.tests.factories import UserFactory
from src.core.org.tests.factories import EmployeeFactory
from src.timesheet.calculations import PlannedOp
from src.timesheet.exceptions import (
    DayLimitExceeded,
    InvalidAllocation,
    NotAWorker,
    PeriodLocked,
    TimeCodeNotFound,
)
from src.timesheet.models import (
    AllocationSource,
    AllocationTarget,
    PeriodStatus,
    TimesheetPeriod,
    WorkAllocation,
)
from src.timesheet.services.allocation import (
    AllocationDTO,
    DayPlan,
    create_allocation,
    delete_allocation,
    fill_day_from_plan,
    fill_days_from_plan,
    replace_day,
    update_allocation,
)
from src.timesheet.tests.factories import TimesheetPeriodFactory, WorkAllocationFactory
from src.timesheet.tests.support import worker

pytestmark = pytest.mark.django_db

DAY = date(2026, 9, 1)  # вторник
SATURDAY = date(2026, 9, 5)


def _actor() -> UUID:
    user_id: UUID = UserFactory.create().id
    return user_id


def _ovh(hours: str = "8") -> AllocationDTO:
    return AllocationDTO(time_code="Я", hours=Decimal(hours), target=AllocationTarget.OVERHEAD)


def _rows(employee_id: UUID, day: date = DAY) -> list[tuple[str, str, Decimal]]:
    return [
        (a.time_code.code, a.target, a.hours)
        for a in WorkAllocation.objects.filter(employee_id=employee_id, date=day)
        .select_related("time_code")
        .order_by("created_at", "id")
    ]


def test_строка_создаётся_в_открытом_периоде_и_заводит_его() -> None:
    profile = worker()

    created = create_allocation(profile.employee_id, DAY, _ovh(), actor_id=_actor())

    assert created.source == AllocationSource.MANUAL
    period = TimesheetPeriod.objects.get(department=profile.employee.department)
    assert (period.month, period.status, period.version) == (date(2026, 9, 1), "draft", 1)


@pytest.mark.parametrize(
    "status",
    [PeriodStatus.ON_REVIEW, PeriodStatus.APPROVED, PeriodStatus.SENT, PeriodStatus.CLOSED],
)
def test_в_закрытом_для_правки_периоде_строку_не_создать(status: PeriodStatus) -> None:
    profile = worker()
    TimesheetPeriodFactory.create(department=profile.employee.department, status=status)

    with pytest.raises(PeriodLocked):
        create_allocation(profile.employee_id, DAY, _ovh(), actor_id=_actor())
    assert not WorkAllocation.objects.exists()


def test_в_переоткрытом_периоде_правка_разрешена() -> None:
    profile = worker()
    TimesheetPeriodFactory.create(
        department=profile.employee.department, status=PeriodStatus.REOPENED, version=2
    )
    create_allocation(profile.employee_id, DAY, _ovh(), actor_id=_actor())
    assert _rows(profile.employee_id) == [("Я", "overhead", Decimal("8.00"))]


def test_больше_24_часов_в_сумме_за_день_нельзя_и_строка_не_остаётся() -> None:
    profile = worker()
    create_allocation(profile.employee_id, DAY, _ovh("20"), actor_id=_actor())

    with pytest.raises(DayLimitExceeded):
        create_allocation(profile.employee_id, DAY, _ovh("5"), actor_id=_actor())

    assert _rows(profile.employee_id) == [("Я", "overhead", Decimal("20.00"))]


def test_сотруднику_без_профиля_разноску_не_вести() -> None:
    with pytest.raises(NotAWorker):
        create_allocation(EmployeeFactory.create().id, DAY, _ovh(), actor_id=_actor())


@pytest.mark.parametrize(
    "dto",
    [
        AllocationDTO(time_code="Я", hours=Decimal("8")),  # разносимое без объекта
        AllocationDTO(time_code="Я", hours=Decimal("8"), target="order"),  # без заказа
        AllocationDTO(time_code="ОТ", hours=Decimal("8"), target="overhead"),
        AllocationDTO(time_code="Я", hours=Decimal("0"), target="overhead"),
        AllocationDTO(time_code="Я", hours=Decimal("8"), target="overhead", order_id=uuid4()),
    ],
)
def test_неверная_строка_отклоняется(dto: AllocationDTO) -> None:
    profile = worker()
    with pytest.raises(InvalidAllocation):
        create_allocation(profile.employee_id, DAY, dto, actor_id=_actor())


def test_неизвестный_код_отклоняется() -> None:
    profile = worker()
    with pytest.raises(TimeCodeNotFound):
        create_allocation(
            profile.employee_id,
            DAY,
            AllocationDTO(time_code="Ж", hours=Decimal("8")),
            actor_id=_actor(),
        )


def test_отпуск_без_объекта_допустим() -> None:
    profile = worker()
    create_allocation(
        profile.employee_id,
        DAY,
        AllocationDTO(time_code="ОТ", hours=Decimal("8")),
        actor_id=_actor(),
    )
    assert _rows(profile.employee_id) == [("ОТ", "", Decimal("8.00"))]


def test_правка_строки_делает_её_ручной_и_проверяет_лимит() -> None:
    profile = worker()
    row = WorkAllocationFactory.create(
        employee=profile.employee, date=DAY, hours=Decimal("4"), source=AllocationSource.PLAN
    )
    WorkAllocationFactory.create(employee=profile.employee, date=DAY, hours=Decimal("16"))
    order = uuid4()

    update_allocation(
        row.id,
        AllocationDTO(time_code="Я", hours=Decimal("6"), target="order", order_id=order),
        actor_id=_actor(),
    )
    row.refresh_from_db()
    assert (row.target, row.order_id, row.hours, row.source) == (
        "order",
        order,
        Decimal("6.00"),
        AllocationSource.MANUAL,
    )
    with pytest.raises(DayLimitExceeded):
        update_allocation(row.id, _ovh("9"), actor_id=_actor())


def test_удаление_строки_только_в_открытом_периоде() -> None:
    profile = worker()
    row = WorkAllocationFactory.create(employee=profile.employee, date=DAY)
    other = WorkAllocationFactory.create(employee=profile.employee, date=date(2026, 10, 1))
    TimesheetPeriodFactory.create(
        department=profile.employee.department,
        month=date(2026, 10, 1),
        status=PeriodStatus.APPROVED,
    )

    delete_allocation(row.id, actor_id=_actor())
    with pytest.raises(PeriodLocked):
        delete_allocation(other.id, actor_id=_actor())

    assert list(WorkAllocation.objects.values_list("id", flat=True)) == [other.id]


def test_сохранение_дня_заменяет_строки_целиком() -> None:
    profile = worker()
    WorkAllocationFactory.create(employee=profile.employee, date=DAY)
    order = uuid4()

    replace_day(
        profile.employee_id,
        DAY,
        [
            AllocationDTO(time_code="Я", hours=Decimal("6"), target="order", order_id=order),
            AllocationDTO(time_code="С", hours=Decimal("2.5"), target="idle"),
        ],
        actor_id=_actor(),
    )

    assert _rows(profile.employee_id) == [
        ("Я", "order", Decimal("6.00")),
        ("С", "idle", Decimal("2.50")),
    ]
    with pytest.raises(DayLimitExceeded):
        replace_day(profile.employee_id, DAY, [_ovh("20"), _ovh("5")], actor_id=_actor())
    replace_day(profile.employee_id, DAY, [], actor_id=_actor())
    assert _rows(profile.employee_id) == []


def test_по_плану_восемь_часов_делятся_поровну_остаток_на_накладные() -> None:
    profile = worker(work_center_id=uuid4())
    plan = [PlannedOp(uuid4(), uuid4(), f"Операция {n}") for n in range(3)]

    assert fill_day_from_plan(profile.employee_id, DAY, plan, actor_id=_actor()) == 1

    rows = list(
        WorkAllocation.objects.filter(employee=profile.employee).order_by("created_at", "id")
    )
    assert [(r.target, r.operation_id, r.hours, r.source) for r in rows] == [
        ("order", plan[0].operation_id, Decimal("2.50"), "plan"),
        ("order", plan[1].operation_id, Decimal("2.50"), "plan"),
        ("order", plan[2].operation_id, Decimal("2.50"), "plan"),
        ("overhead", None, Decimal("0.50"), "plan"),
    ]


def test_по_плану_без_операций_день_на_накладные() -> None:
    profile = worker()
    fill_day_from_plan(profile.employee_id, DAY, [], actor_id=_actor())
    assert _rows(profile.employee_id) == [("Я", "overhead", Decimal("8.00"))]


def test_по_плану_не_трогает_закрытый_день_и_выходной() -> None:
    profile = worker()
    WorkAllocationFactory.create(employee=profile.employee, date=DAY, hours=Decimal("3"))

    assert fill_day_from_plan(profile.employee_id, DAY, [], actor_id=_actor()) == 0
    assert fill_day_from_plan(profile.employee_id, SATURDAY, [], actor_id=_actor()) == 0
    assert _rows(profile.employee_id) == [("Я", "overhead", Decimal("3.00"))]


def test_заполнение_табеля_по_плану_одной_транзакцией() -> None:
    profile = worker()
    days = [date(2026, 9, d) for d in (1, 2, 3, 5)]
    filled = fill_days_from_plan(
        [DayPlan(profile.employee_id, d, []) for d in days], actor_id=_actor()
    )
    assert filled == 3
    assert WorkAllocation.objects.filter(employee=profile.employee).count() == 3
