"""Админка «Производства»: справочники правит начальник производства, заказ только виден,
действие «Пересчитать план» идёт через сервис; списки без N+1."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from src.core.accounts.groups import PRODUCTION_HEAD, PROJECT_MANAGER
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.production.models import JournalKind, WorkCenter
from src.production.tests.support import launch_order, make_plant

pytestmark = pytest.mark.django_db


def _staff(*groups: str) -> Client:
    sync_group_permissions()
    user: User = UserFactory.create(is_staff=True)
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    client = Client()
    client.force_login(user)
    return client


def test_начальник_производства_заводит_участок() -> None:
    client = _staff(PRODUCTION_HEAD)
    response = client.post(
        "/admin/production/workcenter/add/",
        {
            "code": "meh",
            "short_name": "Мех",
            "name": "Мехобработка",
            "hourly_rate": "1700",
            "capacity": "2",
            "phase": "prod",
            "sort_order": "0",
            "is_active": "on",
        },
    )
    assert response.status_code == 302, response.content[:800]
    assert WorkCenter.objects.filter(code="meh").exists()


def test_менеджер_проекта_справочник_участков_не_правит() -> None:
    client = _staff(PROJECT_MANAGER)
    assert client.get("/admin/production/workcenter/add/").status_code == 403


def test_заказ_в_админке_только_для_чтения_а_пересчёт_плана_через_сервис() -> None:
    order = launch_order()
    client = _staff(PRODUCTION_HEAD)
    page = client.get(f"/admin/production/productionorder/{order.id}/change/")
    assert page.status_code == 200
    response = client.post(
        "/admin/production/productionorder/",
        {"action": "replan_action", "_selected_action": [str(order.id)]},
    )
    assert response.status_code == 302
    assert order.journal.filter(kind=JournalKind.PLAN, text__startswith="План пересчитан").exists()


def test_список_заказов_в_админке_не_делает_n_plus_1() -> None:
    client = _staff(PRODUCTION_HEAD)
    plant = make_plant()

    def _count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/admin/production/productionorder/").status_code == 200
        return len(ctx.captured_queries)

    launch_order(plant=plant)
    few = _count()
    for _ in range(5):
        launch_order(plant=plant)
    assert _count() == few
