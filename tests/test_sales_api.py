"""API заявок: права — и разрешение, и запрет; `abilities`; доска без N+1."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import ESTIMATOR, PRODUCTION_HEAD, PROJECT_MANAGER
from src.core.identity.tests.factories import PartyFactory
from src.production.models import ProductionOrder
from src.production.tests.support import client_for, user_with_employee
from src.sales.models import InquiryStage, InquiryStageApproval
from src.sales.tests.factories import LossReasonFactory
from tests.sales_support import make_inquiry, make_shop

pytestmark = pytest.mark.django_db

BASE = "/api/v1/sales"


def _post(client: Client, url: str, data: dict[str, Any] | None = None) -> Any:
    return client.post(url, data or {}, content_type="application/json")


def _create(client: Client, template_id: str) -> Any:
    return _post(
        client,
        f"{BASE}/inquiries",
        {
            "customer_id": str(PartyFactory.create().id),
            "object_name": "Котельная",
            "template_id": template_id,
            "quantity": "2",
            "due_date": str(timezone.localdate() + timedelta(days=90)),
        },
    )


def test_менеджер_проекта_заводит_заявку_себе_экономист_нет() -> None:
    shop = make_shop()
    manager_user, manager = user_with_employee(PROJECT_MANAGER)
    economist_user, _ = user_with_employee(ESTIMATOR)

    created = _create(client_for(manager_user), str(shop.template.id))
    assert created.status_code == 200, created.content
    body = created.json()
    assert body["manager_id"] == str(manager.id)
    assert body["product_name"] == "Шкаф управления АСУ ТП"
    assert body["abilities"]["can_edit"] is True
    assert body["abilities"]["can_launch"] is False

    assert _create(client_for(economist_user), str(shop.template.id)).status_code == 403


def test_чужую_заявку_менеджер_не_правит_а_экономист_считает() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop)
    other_user, _ = user_with_employee(PROJECT_MANAGER)
    economist_user, _ = user_with_employee(ESTIMATOR)

    card = client_for(other_user).get(f"{BASE}/inquiries/{inquiry.id}").json()
    assert card["abilities"]["can_edit"] is False
    assert card["abilities"]["can_edit_calculation"] is False
    assert (
        _post(
            client_for(other_user), f"{BASE}/inquiries/{inquiry.id}/fill-from-template"
        ).status_code
        == 403
    )
    assert (
        _post(
            client_for(other_user),
            f"{BASE}/inquiries/{inquiry.id}/lose",
            {"reason_id": str(LossReasonFactory.create().id)},
        ).status_code
        == 403
    )

    filled = _post(client_for(economist_user), f"{BASE}/inquiries/{inquiry.id}/fill-from-template")
    assert filled.status_code == 200, filled.content
    assert len(filled.json()["operations"]) == 3
    assert filled.json()["totals"]["materials"] == "136000.0000"


def test_полный_путь_через_api_до_запуска_начальником_производства() -> None:
    shop = make_shop()
    manager_user, manager = user_with_employee(PROJECT_MANAGER)
    economist_user, economist = user_with_employee(ESTIMATOR)
    shop.economist = economist
    head_user, _ = user_with_employee(PRODUCTION_HEAD)
    inquiry = make_inquiry(shop, manager=manager)
    InquiryStageApproval.objects.filter(inquiry=inquiry, stage=InquiryStage.CALC).update(
        responsible=economist
    )
    manager_client, economist_client = client_for(manager_user), client_for(economist_user)

    moved = _post(manager_client, f"{BASE}/inquiries/{inquiry.id}/stage", {"to": "calc"})
    assert moved.status_code == 200, moved.content
    _post(economist_client, f"{BASE}/inquiries/{inquiry.id}/fill-from-template")
    _post(economist_client, f"{BASE}/inquiries/{inquiry.id}/plan", {})
    to_approval = _post(
        economist_client, f"{BASE}/inquiries/{inquiry.id}/stage", {"to": "approval"}
    )
    assert to_approval.status_code == 200, to_approval.content

    launch = {
        "planned_start": str(timezone.localdate() + timedelta(days=7)),
        "due_date": str(timezone.localdate() + timedelta(days=90)),
    }
    assert _post(manager_client, f"{BASE}/inquiries/{inquiry.id}/launch", launch).status_code == 403
    approved = _post(manager_client, f"{BASE}/inquiries/{inquiry.id}/stages/approval/approve")
    assert approved.status_code == 200, approved.content
    launched = _post(client_for(head_user), f"{BASE}/inquiries/{inquiry.id}/launch", launch)
    assert launched.status_code == 200, launched.content
    assert ProductionOrder.objects.filter(id=launched.json()["order_id"]).exists()
    card = manager_client.get(f"{BASE}/inquiries/{inquiry.id}").json()
    assert card["stage"] == "launched"
    assert card["abilities"]["can_edit"] is False


def test_мои_визы_экономиста_после_перевода_в_просчёт() -> None:
    shop = make_shop()
    manager_user, manager = user_with_employee(PROJECT_MANAGER)
    economist_user, economist = user_with_employee(ESTIMATOR)
    head_user, _ = user_with_employee(PRODUCTION_HEAD)
    inquiry = make_inquiry(shop, manager=manager)
    InquiryStageApproval.objects.filter(inquiry=inquiry, stage=InquiryStage.CALC).update(
        responsible=economist
    )
    client = client_for(economist_user)
    assert client.get(f"{BASE}/my-visas").json() == []

    # Начальник производства не менеджер заявки и не ответственный — переводить не вправе.
    denied = _post(client_for(head_user), f"{BASE}/inquiries/{inquiry.id}/stage", {"to": "calc"})
    assert denied.status_code == 403
    _post(client_for(manager_user), f"{BASE}/inquiries/{inquiry.id}/stage", {"to": "calc"})

    [visa] = client.get(f"{BASE}/my-visas").json()
    assert (visa["inquiry_id"], visa["stage"]) == (str(inquiry.id), "calc")


def test_доска_заявок_не_делает_n_plus_1() -> None:
    shop = make_shop()
    user, _ = user_with_employee(PROJECT_MANAGER)
    client = client_for(user)

    def _count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(f"{BASE}/board").status_code == 200
        return len(ctx.captured_queries)

    make_inquiry(shop)
    few = _count()
    for _ in range(5):
        make_inquiry(shop)
    assert _count() == few
