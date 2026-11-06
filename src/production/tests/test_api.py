"""API «Производства»: права — и разрешение, и запрет; `abilities` совпадают с тем, что
пускают эндпоинты; доска, Гант и списки без N+1."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import DESIGNER, PRODUCTION_HEAD, PROJECT_MANAGER
from src.production.models import (
    Operation,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
)
from src.production.tests.support import client_for, launch_order, make_plant, user_with_employee

pytestmark = pytest.mark.django_db


def make_uploaded_file(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 demo", content_type="application/pdf")


BASE = "/api/v1/production"


def _post(client: Client, url: str, data: dict[str, Any] | None = None) -> Any:
    return client.post(url, data or {}, content_type="application/json")


def _patch(client: Client, url: str, data: dict[str, Any]) -> Any:
    return client.patch(url, data, content_type="application/json")


def _in_work(order: ProductionOrder) -> None:
    ProductionOrder.objects.filter(id=order.id).update(stage=OrderStage.PREP)


def test_доску_читает_любой_аутентифицированный_но_не_аноним() -> None:
    launch_order()
    user, _ = user_with_employee()
    assert client_for(user).get(f"{BASE}/board").status_code == 200
    assert Client().get(f"{BASE}/board").status_code == 401


def test_ответственный_за_этап_видит_способность_визы_и_переводит() -> None:
    order = launch_order()
    user, me = user_with_employee()
    OrderStageApproval.objects.filter(order=order, stage=OrderStage.LAUNCH).update(responsible=me)
    client = client_for(user)

    card = client.get(f"{BASE}/orders/{order.id}").json()
    assert card["abilities"] == {"can_move": True, "can_approve_stage": True}
    assert card["order_abilities"]["can_plan"] is False

    moved = _post(client, f"{BASE}/orders/{order.id}/stage", {"to": "prep"})
    assert moved.status_code == 200, moved.content
    assert moved.json()["stage"] == "prep"


def test_посторонний_не_переводит_и_не_визирует_этап() -> None:
    order = launch_order()
    user, _ = user_with_employee(PROJECT_MANAGER)
    client = client_for(user)

    card = client.get(f"{BASE}/orders/{order.id}").json()
    assert card["abilities"] == {"can_move": False, "can_approve_stage": False}
    assert _post(client, f"{BASE}/orders/{order.id}/stage", {"to": "prep"}).status_code == 403
    assert _post(client, f"{BASE}/orders/{order.id}/stages/launch/approve").status_code == 403


def test_начальник_производства_переводит_без_визы_с_визой_за_ответственного() -> None:
    order = launch_order()
    head, me = user_with_employee(PRODUCTION_HEAD)
    response = _post(client_for(head), f"{BASE}/orders/{order.id}/stage", {"to": "prep"})
    assert response.status_code == 200, response.content
    visa = OrderStageApproval.objects.get(order=order, stage=OrderStage.LAUNCH)
    assert visa.approved_by_id == me.id


def test_менеджер_заказа_без_визы_получает_409() -> None:
    manager_user, manager = user_with_employee(PROJECT_MANAGER)
    order = launch_order(manager=manager)
    response = _post(client_for(manager_user), f"{BASE}/orders/{order.id}/stage", {"to": "prep"})
    assert response.status_code == 409
    assert response.json()["code"] == "visa_required"


def test_ответственный_за_операцию_ведёт_её_ход_а_посторонний_нет() -> None:
    order = launch_order()
    _in_work(order)
    kd = Operation.objects.get(order=order, name="КД")
    owner, _ = user_with_employee()
    kd.responsible = owner.employee
    kd.save(update_fields=["responsible"])
    stranger, _ = user_with_employee(PROJECT_MANAGER)

    denied = _post(client_for(stranger), f"{BASE}/operations/{kd.id}/status", {"status": "work"})
    assert denied.status_code == 403

    card = client_for(owner).get(f"{BASE}/operations/{kd.id}").json()
    assert card["operation"]["abilities"]["can_change_status"] is True
    assert card["operation"]["abilities"]["can_edit_plan"] is False
    ok = _post(client_for(owner), f"{BASE}/operations/{kd.id}/status", {"status": "work"})
    assert ok.status_code == 200, ok.content
    progress = _post(client_for(owner), f"{BASE}/operations/{kd.id}/progress", {"progress": 100})
    assert progress.json()["operation"]["status"] == "check"
    visa = _post(client_for(owner), f"{BASE}/operations/{kd.id}/approve", {"comment": "ок"})
    assert visa.status_code == 200, visa.content
    assert visa.json()["operation"]["status"] == OperationStatus.DONE


def test_визу_операции_не_ставит_посторонний() -> None:
    order = launch_order()
    _in_work(order)
    kd = Operation.objects.get(order=order, name="КД")
    stranger, _ = user_with_employee(DESIGNER)
    response = _post(client_for(stranger), f"{BASE}/operations/{kd.id}/approve")
    assert response.status_code == 403


def test_план_правит_начальник_производства_а_не_ответственный() -> None:
    order = launch_order()
    assembly = Operation.objects.get(order=order, name="Сборка")
    owner, _ = user_with_employee()
    assembly.responsible = owner.employee
    assembly.save(update_fields=["responsible"])

    denied = _patch(client_for(owner), f"{BASE}/operations/{assembly.id}", {"people": 1})
    assert denied.status_code == 403

    head, _ = user_with_employee(PRODUCTION_HEAD)
    ok = _patch(client_for(head), f"{BASE}/operations/{assembly.id}", {"people": 1})
    assert ok.status_code == 200, ok.content
    assert ok.json()["operation"]["people"] == 1
    cleared = _patch(client_for(head), f"{BASE}/operations/{assembly.id}", {"not_before": None})
    assert cleared.status_code == 200
    assert (
        _post(client_for(owner), f"{BASE}/orders/{order.id}/shift", {"days": 1}).status_code == 403
    )
    assert (
        _post(client_for(head), f"{BASE}/orders/{order.id}/shift", {"days": 1}).status_code == 200
    )


def test_документы_ведут_конструктор_и_технолог() -> None:
    order = launch_order()
    designer, _ = user_with_employee(DESIGNER)
    stranger, _ = user_with_employee(PROJECT_MANAGER)
    payload = {"doc_type_code": "production.kd", "file": make_uploaded_file("kd.pdf")}

    assert (
        client_for(stranger).post(f"{BASE}/orders/{order.id}/documents", payload).status_code == 403
    )
    payload["file"] = make_uploaded_file("kd.pdf")
    response = client_for(designer).post(f"{BASE}/orders/{order.id}/documents", payload)
    assert response.status_code == 200, response.content
    [doc] = response.json()
    assert doc["doc_type_name"] == "КД"

    approved = _post(
        client_for(designer), f"{BASE}/orders/{order.id}/documents/{doc['document_id']}/approve"
    )
    assert approved.json()[0]["approved_by_name"] != ""
    assert client_for(designer).get(f"{BASE}/orders/{order.id}").json()["has_kd"] is True

    annulled = client_for(designer).delete(
        f"{BASE}/orders/{order.id}/documents/{doc['document_id']}"
    )
    assert annulled.json() == []


def test_комментарий_пишет_сотрудник_в_журнал() -> None:
    order = launch_order()
    user, _ = user_with_employee()
    response = _post(client_for(user), f"{BASE}/orders/{order.id}/comments", {"text": "Привет"})
    assert response.status_code == 200
    journal = client_for(user).get(f"{BASE}/orders/{order.id}/journal?kind=comment").json()
    assert [row["text"] for row in journal] == ["Привет"]


def test_мои_визы_показывают_этап_и_операцию_на_визе() -> None:
    order = launch_order(planned_start=timezone.localdate())
    user, me = user_with_employee()
    OrderStageApproval.objects.filter(order=order, stage=OrderStage.LAUNCH).update(responsible=me)
    visas = client_for(user).get(f"{BASE}/my-visas").json()
    assert [(v["kind"], v["order_id"]) for v in visas] == [("stage", str(order.id))]


def _count(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


@pytest.mark.parametrize("url", ["/board", "/gantt", "/my-visas"])
def test_списки_не_делают_n_plus_1(url: str) -> None:
    user, me = user_with_employee(PRODUCTION_HEAD)
    client = client_for(user)
    plant = make_plant()

    def _orders(n: int) -> None:
        for _ in range(n):
            order = launch_order(plant=plant)
            OrderStageApproval.objects.filter(order=order, stage=OrderStage.LAUNCH).update(
                responsible=me
            )

    _orders(2)
    few = _count(client, f"{BASE}{url}")
    _orders(6)
    many = _count(client, f"{BASE}{url}")
    assert many == few
