"""Статусы табеля подразделения: подача с блокирующими проверками, визы менеджеров,
согласование, передача в 1С, закрытие, переоткрытие с версией — и запрещённые
переходы."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.core.accounts.tests.factories import UserFactory
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory
from src.timesheet import selectors
from src.timesheet.exceptions import (
    BlockingChecks,
    InvalidMonth,
    InvalidTransition,
    ManagerConfirmationsMissing,
    NothingToConfirm,
    PeriodLocked,
    ReasonRequired,
)
from src.timesheet.models import PeriodEventKind, PeriodStatus, TimesheetPeriod
from src.timesheet.services import period as svc
from src.timesheet.services.allocation import AllocationDTO, create_allocation
from src.timesheet.tests.factories import TimesheetPeriodFactory, WorkAllocationFactory
from src.timesheet.tests.support import SEPTEMBER, TODAY, fill_month, worker

pytestmark = pytest.mark.django_db


def _actor() -> UUID:
    user_id: UUID = UserFactory.create().id
    return user_id


def _ready_department() -> tuple[UUID, UUID]:
    """Подразделение с одним работником и полностью закрытым сентябрём."""

    profile = worker()
    fill_month(profile.employee, SEPTEMBER)
    return profile.employee.department_id, profile.employee_id


def _status(department_id: UUID) -> tuple[str, int]:
    period = TimesheetPeriod.objects.get(department_id=department_id, month=SEPTEMBER)
    return period.status, period.version


def _kinds(department_id: UUID) -> list[str]:
    period = TimesheetPeriod.objects.get(department_id=department_id, month=SEPTEMBER)
    return [e.kind for e in period.events.order_by("created_at", "id")]


def test_полный_цикл_табеля_с_переоткрытием() -> None:
    dep, _ = _ready_department()
    actor = _actor()

    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor)
    svc.approve_period(dep, SEPTEMBER, order_managers={}, actor_id=actor)
    timesheet, cost = svc.send_period(dep, SEPTEMBER, order_numbers={}, actor_id=actor)
    assert _status(dep) == (PeriodStatus.SENT, 1)
    assert (timesheet["version"], len(timesheet["entries"]), len(cost["rows"])) == (1, 22, 1)

    svc.close_period(dep, SEPTEMBER, actor_id=actor)
    svc.reopen_period(dep, SEPTEMBER, "Пересчёт больничного", actor_id=actor)

    assert _status(dep) == (PeriodStatus.REOPENED, 2)
    assert _kinds(dep) == [
        PeriodEventKind.SUBMITTED,
        PeriodEventKind.APPROVED,
        PeriodEventKind.SENT,
        PeriodEventKind.CLOSED,
        PeriodEventKind.REOPENED,
    ]
    sent = TimesheetPeriod.objects.get(department_id=dep).events.get(kind=PeriodEventKind.SENT)
    assert sent.comment == "табель 22 строк, база распределения 1 строк"
    # Переоткрытый период правится и уходит в 1С следующей версией.
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor)
    svc.approve_period(dep, SEPTEMBER, order_managers={}, actor_id=actor)
    timesheet, _ = svc.send_period(dep, SEPTEMBER, order_numbers={}, actor_id=actor)
    assert timesheet["version"] == 2


def test_блокирующие_замечания_не_дают_подать() -> None:
    profile = worker(full_name="Иванов И.И.")
    fill_month(profile.employee, SEPTEMBER, skip=(30,))

    with pytest.raises(BlockingChecks) as error:
        svc.submit_period(profile.employee.department_id, SEPTEMBER, today=TODAY, actor_id=_actor())

    assert error.value.details == ["Иванов И.И.: не закрыты дни 30"]
    state = selectors.period_state(profile.employee.department_id, SEPTEMBER)
    assert (state.status, state.version) == (PeriodStatus.DRAFT, 1)


def test_предупреждения_подать_не_мешают() -> None:
    dep, employee_id = _ready_department()
    WorkAllocationFactory.create(employee_id=employee_id, date=date(2026, 9, 1), hours=Decimal("2"))
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=_actor())
    assert _status(dep) == (PeriodStatus.ON_REVIEW, 1)


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (PeriodStatus.ON_REVIEW, "submit"),
        (PeriodStatus.APPROVED, "submit"),
        (PeriodStatus.DRAFT, "approve"),
        (PeriodStatus.SENT, "approve"),
        (PeriodStatus.DRAFT, "send"),
        (PeriodStatus.ON_REVIEW, "send"),
        (PeriodStatus.APPROVED, "close"),
        (PeriodStatus.DRAFT, "reopen"),
        (PeriodStatus.APPROVED, "reopen"),
        (PeriodStatus.DRAFT, "return"),
        (PeriodStatus.APPROVED, "return"),
    ],
)
def test_запрещённые_переходы(status: PeriodStatus, action: str) -> None:
    dep, _ = _ready_department()
    TimesheetPeriodFactory.create(department_id=dep, status=status)
    actor = _actor()
    calls = {
        "submit": lambda: svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor),
        "approve": lambda: svc.approve_period(dep, SEPTEMBER, order_managers={}, actor_id=actor),
        "send": lambda: svc.send_period(dep, SEPTEMBER, order_numbers={}, actor_id=actor),
        "close": lambda: svc.close_period(dep, SEPTEMBER, actor_id=actor),
        "reopen": lambda: svc.reopen_period(dep, SEPTEMBER, "причина", actor_id=actor),
        "return": lambda: svc.return_period(dep, SEPTEMBER, "причина", actor_id=actor),
    }

    with pytest.raises(InvalidTransition):
        calls[action]()

    assert _status(dep) == (status, 1)
    assert _kinds(dep) == []


def test_возврат_и_переоткрытие_требуют_причину() -> None:
    dep, _ = _ready_department()
    TimesheetPeriodFactory.create(department_id=dep, status=PeriodStatus.ON_REVIEW)
    with pytest.raises(ReasonRequired):
        svc.return_period(dep, SEPTEMBER, "  ", actor_id=_actor())
    with pytest.raises(ReasonRequired):
        svc.reopen_period(dep, SEPTEMBER, "", actor_id=_actor())


def test_возврат_после_переоткрытия_оставляет_период_открытым_для_корректировки() -> None:
    dep, _ = _ready_department()
    TimesheetPeriodFactory.create(department_id=dep, status=PeriodStatus.ON_REVIEW, version=2)
    svc.return_period(dep, SEPTEMBER, "Не та операция", actor_id=_actor())
    assert _status(dep) == (PeriodStatus.REOPENED, 2)

    other, _ = _ready_department()
    TimesheetPeriodFactory.create(department_id=other, status=PeriodStatus.ON_REVIEW)
    svc.return_period(other, SEPTEMBER, "Не та операция", actor_id=_actor())
    assert _status(other) == (PeriodStatus.DRAFT, 1)


def test_утвердить_можно_только_после_виз_всех_менеджеров_с_часами() -> None:
    dep, employee_id = _ready_department()
    order_a, order_b, order_free = uuid4(), uuid4(), uuid4()
    for order in (order_a, order_b, order_free):
        WorkAllocationFactory.create(
            employee_id=employee_id,
            date=date(2026, 9, 5),
            target="order",
            order_id=order,
            hours=Decimal("1"),
        )
    manager_a, manager_b = EmployeeFactory.create(), EmployeeFactory.create()
    managers = {order_a: manager_a.id, order_b: manager_b.id}  # order_free без менеджера
    actor = _actor()
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor)

    svc.confirm_manager_hours(dep, SEPTEMBER, manager_a.id, order_managers=managers, actor_id=actor)
    with pytest.raises(ManagerConfirmationsMissing):
        svc.approve_period(dep, SEPTEMBER, order_managers=managers, actor_id=actor)
    with pytest.raises(NothingToConfirm):  # повторная виза
        svc.confirm_manager_hours(
            dep, SEPTEMBER, manager_a.id, order_managers=managers, actor_id=actor
        )
    with pytest.raises(NothingToConfirm):  # менеджер без часов в табеле
        svc.confirm_manager_hours(
            dep, SEPTEMBER, EmployeeFactory.create().id, order_managers=managers, actor_id=actor
        )

    svc.confirm_manager_hours(dep, SEPTEMBER, manager_b.id, order_managers=managers, actor_id=actor)
    svc.approve_period(dep, SEPTEMBER, order_managers=managers, actor_id=actor)
    assert _status(dep) == (PeriodStatus.APPROVED, 1)


def test_возврат_снимает_визы_менеджеров() -> None:
    dep, employee_id = _ready_department()
    order = uuid4()
    WorkAllocationFactory.create(
        employee_id=employee_id, date=date(2026, 9, 5), target="order", order_id=order
    )
    manager = EmployeeFactory.create()
    managers = {order: manager.id}
    actor = _actor()
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor)
    svc.confirm_manager_hours(dep, SEPTEMBER, manager.id, order_managers=managers, actor_id=actor)
    svc.return_period(dep, SEPTEMBER, "Исправить заказ", actor_id=actor)
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=actor)

    with pytest.raises(ManagerConfirmationsMissing):
        svc.approve_period(dep, SEPTEMBER, order_managers=managers, actor_id=actor)


def test_виза_менеджера_только_на_согласовании() -> None:
    dep, _ = _ready_department()
    with pytest.raises(InvalidTransition):
        svc.confirm_manager_hours(dep, SEPTEMBER, uuid4(), order_managers={}, actor_id=_actor())


def test_поданный_табель_закрыт_для_правки_разноски() -> None:
    dep, employee_id = _ready_department()
    svc.submit_period(dep, SEPTEMBER, today=TODAY, actor_id=_actor())
    with pytest.raises(PeriodLocked):
        create_allocation(
            employee_id,
            date(2026, 9, 5),
            AllocationDTO(time_code="Я", hours=Decimal("1"), target="overhead"),
            actor_id=_actor(),
        )


def test_месяц_не_первым_числом_отклоняется() -> None:
    with pytest.raises(InvalidMonth):
        svc.submit_period(
            DepartmentFactory.create().id, date(2026, 9, 2), today=TODAY, actor_id=_actor()
        )
