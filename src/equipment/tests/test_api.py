"""API экрана «Оборудование»: права — и разрешение, и запрет; `abilities` совпадают
с тем, что пускают эндпоинты; списки без N+1."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import FOREMAN, PRODUCTION_HEAD
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.core.events.models import OutboxEvent
from src.core.org.tests.factories import EmployeeFactory
from src.equipment.models import Equipment, EquipmentStatus, RepairKind, RepairStatus, RuntimeLog
from src.equipment.tests.factories import (
    DownReasonFactory,
    EquipmentFactory,
    FailureCategoryFactory,
    IdleReasonFactory,
    MaintenanceRecordFactory,
    MaintenanceTypeFactory,
    RepairFactory,
    RepairWorkerFactory,
    RuntimeLogFactory,
)

pytestmark = pytest.mark.django_db

BASE = "/api/v1/equipment"


def _client(*groups: str) -> Client:
    sync_group_permissions()
    user: User = UserFactory.create()
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    client = Client()
    client.force_login(user)
    return client


def _send(client: Client, method: str, url: str, data: dict[str, Any] | None = None) -> Any:
    return getattr(client, method)(url, data or {}, content_type="application/json")


def _yesterday_9() -> datetime:
    day = timezone.localdate() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(9, 0)))


def test_начальник_производства_заводит_станок_и_вид_то() -> None:
    client = _client(PRODUCTION_HEAD)

    created = _send(
        client,
        "post",
        f"{BASE}/machines",
        {"inventory_no": "ИН-0099", "name": "Пресс", "operating_hours_initial": "1200"},
    )
    assert created.status_code == 200, created.content
    body = created.json()
    assert body["operating_hours"] == "1200.00"
    assert body["abilities"]["can_edit"] is True
    mtype = _send(
        client,
        "post",
        f"{BASE}/machines/{body['id']}/maintenance-types",
        {"code": "ТО-1", "interval_hours": "250", "scope": "смазка"},
    )
    assert mtype.status_code == 200
    # ТО ещё не проводилось — отсчёт от нуля моточасов (как в прототипе): 1200 > 250.
    assert mtype.json()["maintenance"][0]["state"] == "overdue"


def test_мастер_вносит_смену_но_не_заводит_станки() -> None:
    client = _client(FOREMAN)
    equipment = EquipmentFactory.create()
    reason = IdleReasonFactory.create()

    created = _send(client, "post", f"{BASE}/machines", {"inventory_no": "X", "name": "Y"})
    shift = _send(
        client,
        "put",
        f"{BASE}/machines/{equipment.id}/runtime",
        {
            "date": (timezone.localdate() - timedelta(days=1)).isoformat(),
            "run": "6",
            "idle": "1.5",
            "idle_reason_id": str(reason.id),
        },
    )

    assert created.status_code == 403
    assert shift.status_code == 200, shift.content
    abilities = shift.json()["abilities"]
    assert abilities["can_log_runtime"] is True
    assert abilities["can_edit"] is False
    assert RuntimeLog.objects.get(equipment=equipment).run == Decimal("6.00")


def test_без_роли_всё_видно_но_ничего_не_изменить() -> None:
    client = _client()
    equipment = EquipmentFactory.create()
    repair = RepairFactory.create(equipment=equipment)

    assert client.get(f"{BASE}/machines").status_code == 200
    card = client.get(f"{BASE}/machines/{equipment.id}")
    assert card.status_code == 200
    assert not any(card.json()["abilities"].values())
    assert client.get(f"{BASE}/repairs/{repair.id}").json()["abilities"] == {
        "can_edit": False,
        "can_start": False,
        "can_close": False,
    }
    shift = _send(
        client,
        "put",
        f"{BASE}/machines/{equipment.id}/runtime",
        {"date": timezone.localdate().isoformat(), "run": "1"},
    )
    status = _send(client, "post", f"{BASE}/machines/{equipment.id}/status", {"status": "idle"})
    close = _send(client, "post", f"{BASE}/repairs/{repair.id}/close", {})
    assert (shift.status_code, status.status_code, close.status_code) == (403, 403, 403)


def test_анонимный_запрос_отклоняется() -> None:
    assert Client().get(f"{BASE}/machines").status_code == 401


def test_больше_24_часов_через_api_это_400_а_не_500() -> None:
    client = _client(FOREMAN)
    equipment = EquipmentFactory.create()
    response = _send(
        client,
        "put",
        f"{BASE}/machines/{equipment.id}/runtime",
        {"date": timezone.localdate().isoformat(), "run": "20", "setup": "5"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "day_overflow"


def test_полный_цикл_аварии_через_api() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    client = _client(FOREMAN)
    equipment = EquipmentFactory.create()
    worker = EmployeeFactory.create()
    category = FailureCategoryFactory.create()
    started = _yesterday_9()

    created = _send(
        client,
        "post",
        f"{BASE}/repairs",
        {
            "equipment_id": str(equipment.id),
            "kind": "fail",
            "started_at": started.isoformat(),
            "description": "Утечка гидравлики",
            "workers": [{"employee_id": str(worker.id), "hours": "2"}],
        },
    )
    assert created.status_code == 200, created.content
    repair = created.json()
    assert repair["abilities"] == {"can_edit": True, "can_start": True, "can_close": True}
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.REPAIR

    started_work = _send(client, "post", f"{BASE}/repairs/{repair['id']}/start")
    assert started_work.json()["status"] == "work"
    no_category = _send(
        client,
        "post",
        f"{BASE}/repairs/{repair['id']}/close",
        {"finished_at": (started + timedelta(hours=2)).isoformat()},
    )
    assert no_category.status_code == 400
    _send(
        client,
        "patch",
        f"{BASE}/repairs/{repair['id']}",
        {
            "kind": "fail",
            "started_at": started.isoformat(),
            "description": "Утечка гидравлики",
            "category_id": str(category.id),
            "fix": "Замена уплотнений",
            "workers": [{"employee_id": str(worker.id), "hours": "2"}],
        },
    )
    closed = _send(
        client,
        "post",
        f"{BASE}/repairs/{repair['id']}/close",
        {"finished_at": (started + timedelta(hours=2)).isoformat()},
    )

    assert closed.status_code == 200, closed.content
    body = closed.json()
    assert body["status"] == RepairStatus.DONE
    assert body["downtime_hours"] == "2.0"
    assert body["labor_hours"] == "2.00"
    assert body["abilities"]["can_close"] is False
    assert OutboxEvent.objects.filter(event_type="equipment.repair_closed").count() == 1
    again = _send(client, "post", f"{BASE}/repairs/{repair['id']}/close", {})
    assert again.status_code == 409


def test_провести_то_через_api() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.MAINTENANCE)
    client = _client(PRODUCTION_HEAD)
    mtype = MaintenanceTypeFactory.create()
    worker = EmployeeFactory.create()
    started = _yesterday_9()

    response = _send(
        client,
        "post",
        f"{BASE}/maintenance-types/{mtype.id}/perform",
        {
            "started_at": started.isoformat(),
            "finished_at": (started + timedelta(hours=3)).isoformat(),
            "workers": [{"employee_id": str(worker.id), "hours": "3"}],
            "comment": "заменён фильтр",
        },
    )

    assert response.status_code == 200, response.content
    assert response.json()["kind"] == "maintenance"
    card = client.get(f"{BASE}/machines/{mtype.equipment_id}").json()
    assert card["maintenance"][0]["last_date"] == started.date().isoformat()


def _queries(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


def _machines(count: int) -> None:
    category = FailureCategoryFactory.create()
    for _ in range(count):
        equipment = EquipmentFactory.create()
        mtype = MaintenanceTypeFactory.create(equipment=equipment)
        MaintenanceRecordFactory.create(maintenance_type=mtype)
        RuntimeLogFactory.create(equipment=equipment)
        repair = RepairFactory.create(
            equipment=equipment,
            status=RepairStatus.DONE,
            finished_at=timezone.now(),
            category=category,
        )
        RepairWorkerFactory.create(repair=repair)


@pytest.mark.parametrize("url", ["/machines", "/dashboard", "/repairs"])
def test_списки_экрана_не_делают_n_plus_1(url: str) -> None:
    client = _client()
    _machines(2)
    small = _queries(client, BASE + url)
    _machines(6)
    assert _queries(client, BASE + url) == small
