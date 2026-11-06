"""API экрана «Табель»: права — и разрешение, и запрет; `abilities` совпадают с тем, что
пускают эндпоинты; пакеты 1С скачиваются файлом; сетка месяца без N+1."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from src.core.accounts.groups import ESTIMATOR, FOREMAN, PRODUCTION_HEAD
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.core.org.models import Department, Employee
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory
from src.timesheet import production_link
from src.timesheet.models import PeriodStatus, WorkAllocation
from src.timesheet.tests.factories import TimesheetPeriodFactory, WorkAllocationFactory
from src.timesheet.tests.support import SEPTEMBER, fill_month, worker

pytestmark = pytest.mark.django_db

BASE = "/api/v1/timesheet"
PERIOD = BASE + "/departments/{dep}/periods/2026-09-01"
DAY = "2026-09-01"


def _user(*groups: str, department: Department | None = None) -> tuple[User, Employee]:
    sync_group_permissions()
    user = UserFactory.create()
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    employee = EmployeeFactory.create(
        user=user, **({"department": department} if department else {})
    )
    return user, employee


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _post(client: Client, url: str, data: dict[str, Any] | None = None) -> Any:
    return client.post(url, data or {}, content_type="application/json")


def _put_day(client: Client, employee_id: UUID, hours: str = "8") -> Any:
    return client.put(
        f"{BASE}/employees/{employee_id}/days/{DAY}",
        {"rows": [{"time_code": "Я", "hours": hours, "target": "overhead"}]},
        content_type="application/json",
    )


def test_мастер_правит_своё_подразделение_но_не_чужое() -> None:
    own = worker()
    alien = worker()
    foreman, _ = _user(FOREMAN, department=own.employee.department)
    client = _client(foreman)

    assert _put_day(client, own.employee_id).status_code == 200
    assert _put_day(client, alien.employee_id).status_code == 403
    assert not WorkAllocation.objects.filter(employee=alien.employee).exists()


def test_без_прав_разноску_не_править_но_табель_читается() -> None:
    profile = worker()
    user, _ = _user(department=profile.employee.department)
    client = _client(user)

    assert _put_day(client, profile.employee_id).status_code == 403
    grid = client.get(PERIOD.format(dep=profile.employee.department_id) + "/grid")
    assert grid.status_code == 200
    assert grid.json()["period"]["abilities"] == {
        "can_edit": False,
        "can_fill_plan": False,
        "can_submit": False,
        "can_confirm_manager": False,
        "can_approve": False,
        "can_return": False,
        "can_send": False,
        "can_close": False,
        "can_reopen": False,
    }
    assert (
        _post(client, PERIOD.format(dep=profile.employee.department_id) + "/submit").status_code
        == 403
    )


def test_руководитель_подразделения_правит_и_подаёт_без_отдельного_права() -> None:
    profile = worker()
    fill_month(profile.employee, SEPTEMBER)
    head, head_employee = _user()
    department = profile.employee.department
    department.head = head_employee
    department.save()
    child = DepartmentFactory.create(parent=department, legal_entity=department.legal_entity)
    child_worker = worker(child)
    client = _client(head)

    grid = client.get(PERIOD.format(dep=department.id) + "/grid").json()
    assert grid["period"]["abilities"]["can_submit"] is True
    assert _put_day(client, child_worker.employee_id).status_code == 200
    submitted = _post(client, PERIOD.format(dep=department.id) + "/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "on_review"


def test_начальник_производства_правит_любое_подразделение_но_не_согласует() -> None:
    profile = worker()
    head, _ = _user(PRODUCTION_HEAD)
    client = _client(head)
    TimesheetPeriodFactory.create(
        department=profile.employee.department, status=PeriodStatus.ON_REVIEW
    )

    assert (
        _post(client, PERIOD.format(dep=profile.employee.department_id) + "/approve").status_code
        == 403
    )
    other = worker()
    assert _put_day(client, other.employee_id).status_code == 200


def test_экономист_согласует_передаёт_в_1с_и_скачивает_пакеты() -> None:
    profile = worker(rate="1200")
    fill_month(profile.employee, SEPTEMBER)
    dep = profile.employee.department_id
    TimesheetPeriodFactory.create(
        department=profile.employee.department, status=PeriodStatus.ON_REVIEW
    )
    economist, _ = _user(ESTIMATOR)
    foreman, _ = _user(FOREMAN, department=profile.employee.department)
    client = _client(economist)

    review = client.get(PERIOD.format(dep=dep) + "/review").json()
    assert review["period"]["abilities"]["can_approve"] is True
    assert review["period"]["abilities"]["can_edit"] is False
    assert _post(_client(foreman), PERIOD.format(dep=dep) + "/approve").status_code == 403

    assert _post(client, PERIOD.format(dep=dep) + "/approve").json()["status"] == "approved"
    sent = _post(client, PERIOD.format(dep=dep) + "/send").json()
    assert (sent["status"], sent["abilities"]["can_close"], sent["abilities"]["can_reopen"]) == (
        "sent",
        True,
        True,
    )

    response = client.get(PERIOD.format(dep=dep) + "/packages/cost_allocation")
    assert response.status_code == 200
    assert response["Content-Disposition"] == (
        'attachment; filename="cost_allocation_2026-09_v1.json"'
    )
    package = json.loads(response.content)
    assert package["rows"] == [
        {
            "employee_code": profile.employee.personnel_number,
            "analytics": f"OVH-{profile.employee.department.code}",
            "hours": "176.00",
            "share": "1.0000",
        }
    ]
    timesheet = json.loads(client.get(PERIOD.format(dep=dep) + "/packages/timesheet").content)
    assert len(timesheet["entries"]) == 22

    reopened = _post(client, PERIOD.format(dep=dep) + "/reopen", {"comment": "Больничный"})
    assert (reopened.json()["status"], reopened.json()["version"]) == ("reopened", 2)
    events = client.get(PERIOD.format(dep=dep) + "/review").json()["events"]
    assert [e["kind"] for e in events] == ["approved", "sent", "reopened"]


def test_блокирующие_замечания_видны_и_подать_нельзя() -> None:
    profile = worker(full_name="Иванов И.И.")
    fill_month(profile.employee, SEPTEMBER, skip=(29, 30))
    head, _ = _user(PRODUCTION_HEAD)
    client = _client(head)

    grid = client.get(PERIOD.format(dep=profile.employee.department_id) + "/grid").json()
    assert grid["checks"] == [
        {
            "is_blocking": True,
            "text": "Иванов И.И.: не закрыты дни 29, 30",
            "employee_id": str(profile.employee_id),
        }
    ]
    assert grid["period"]["abilities"]["can_submit"] is False
    response = _post(client, PERIOD.format(dep=profile.employee.department_id) + "/submit")
    assert response.status_code == 409
    assert response.json()["code"] == "blocking_checks"


def test_виза_менеджера_ставит_только_сам_менеджер(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = worker()
    fill_month(profile.employee, SEPTEMBER)
    order = uuid4()
    WorkAllocationFactory.create(
        employee=profile.employee,
        date=date(2026, 9, 5),
        target="order",
        order_id=order,
        hours=Decimal("4"),
    )
    manager_user, manager = _user()
    stranger, _ = _user()
    monkeypatch.setattr(production_link, "order_managers", lambda ids: {order: manager.id})
    TimesheetPeriodFactory.create(
        department=profile.employee.department, status=PeriodStatus.ON_REVIEW
    )
    dep = profile.employee.department_id

    review = _client(manager_user).get(PERIOD.format(dep=dep) + "/review").json()
    assert review["managers"] == [
        {
            "manager_id": str(manager.id),
            "manager_name": manager.full_name,
            "orders": [{"order_id": str(order), "hours": "4.00"}],
            "confirmed": False,
            "can_confirm": True,
        }
    ]
    assert _post(_client(stranger), PERIOD.format(dep=dep) + "/confirm-manager").status_code == 409
    economist, _ = _user(ESTIMATOR)
    assert _post(_client(economist), PERIOD.format(dep=dep) + "/approve").status_code == 409

    confirmed = _post(_client(manager_user), PERIOD.format(dep=dep) + "/confirm-manager")
    assert confirmed.status_code == 200
    assert confirmed.json()["abilities"]["can_confirm_manager"] is False
    assert _post(_client(economist), PERIOD.format(dep=dep) + "/approve").status_code == 200


def test_диалог_дня_и_строки_разноски() -> None:
    profile = worker()
    head, _ = _user(PRODUCTION_HEAD)
    client = _client(head)

    day = _put_day(client, profile.employee_id, "6").json()
    assert (day["total"], day["can_edit"], [r["hours"] for r in day["rows"]]) == (
        "6.00",
        True,
        ["6.00"],
    )
    created = _post(
        client,
        f"{BASE}/allocations",
        {
            "employee_id": str(profile.employee_id),
            "date": DAY,
            "time_code": "С",
            "hours": "2",
            "target": "idle",
        },
    )
    assert created.status_code == 200
    row_id = created.json()["id"]
    patched = client.patch(
        f"{BASE}/allocations/{row_id}",
        {"time_code": "С", "hours": "3", "target": "idle"},
        content_type="application/json",
    )
    assert patched.json()["hours"] == "3.00"
    too_much = _post(
        client,
        f"{BASE}/allocations",
        {
            "employee_id": str(profile.employee_id),
            "date": DAY,
            "time_code": "Я",
            "hours": "16",
            "target": "overhead",
        },
    )
    assert (too_much.status_code, too_much.json()["code"]) == (400, "day_limit_exceeded")
    assert client.delete(f"{BASE}/allocations/{row_id}").status_code == 204

    filled = _post(client, f"{BASE}/employees/{profile.employee_id}/days/2026-09-02/fill-from-plan")
    assert [(r["target"], r["hours"], r["source"]) for r in filled.json()["rows"]] == [
        ("overhead", "8.00", "plan")
    ]


def test_заполнить_табель_по_плану() -> None:
    profile = worker()
    fill_month(profile.employee, SEPTEMBER, skip=(1, 2))
    head, _ = _user(PRODUCTION_HEAD)
    response = _post(
        _client(head), PERIOD.format(dep=profile.employee.department_id) + "/fill-from-plan"
    )
    assert response.json()["filled_days"] == 2
    assert response.json()["period"]["abilities"]["can_submit"] is True


def test_правка_в_закрытом_периоде_конфликт() -> None:
    profile = worker()
    TimesheetPeriodFactory.create(
        department=profile.employee.department, status=PeriodStatus.APPROVED
    )
    head, _ = _user(PRODUCTION_HEAD)
    response = _put_day(_client(head), profile.employee_id)
    assert (response.status_code, response.json()["code"]) == (409, "period_locked")


def test_месяц_не_первым_числом_400() -> None:
    profile = worker()
    head, _ = _user(PRODUCTION_HEAD)
    url = f"{BASE}/departments/{profile.employee.department_id}/periods/2026-09-02/grid"
    response = _client(head).get(url)
    assert (response.status_code, response.json()["code"]) == (400, "invalid_month")


def test_список_подразделений_со_статусом_табеля() -> None:
    profile = worker()
    TimesheetPeriodFactory.create(department=profile.employee.department, status=PeriodStatus.SENT)
    user, _ = _user()
    rows = _client(user).get(f"{BASE}/departments?month=2026-09-01").json()
    assert [(r["department_id"], r["status"]) for r in rows] == [
        (str(profile.employee.department_id), "sent")
    ]


def test_сетка_месяца_без_n_plus_1() -> None:
    department = DepartmentFactory.create()
    head, _ = _user(PRODUCTION_HEAD)
    client = _client(head)
    url = PERIOD.format(dep=department.id) + "/grid"

    def _count() -> int:
        client.get(url)  # прогрев: сессия, права пользователя
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url).status_code == 200
        return len(ctx.captured_queries)

    for _ in range(2):
        fill_month(worker(department).employee, SEPTEMBER)
    few = _count()
    for _ in range(5):
        fill_month(worker(department).employee, SEPTEMBER)
    many = _count()

    assert few == many
    grid = client.get(url).json()
    assert len(grid["rows"]) == 7
    assert grid["rows"][0]["total"] == "176.00"
    assert grid["by_code"] == [{"code": "Я", "name": "Явка", "hours": "1232.00"}]
