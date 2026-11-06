"""Фасад «Производства» для аналитики: операции нескольких заказов одним запросом,
отгруженные заказы за период."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.production import facade
from src.production.models import OrderStage, ProductionOrder
from src.production.tests.support import launch_order, make_plant

pytestmark = pytest.mark.django_db


def test_операции_нескольких_заказов_одним_запросом() -> None:
    plant = make_plant()
    orders = [launch_order(plant=plant) for _ in range(3)]

    with CaptureQueriesContext(connection) as queries:
        ops = facade.list_operations_for_orders(o.id for o in orders[:2])

    assert len(queries.captured_queries) == 1
    assert {op.order_id for op in ops} == {orders[0].id, orders[1].id}
    assert [op.name for op in ops if op.order_id == orders[0].id] == ["КД", "Сборка", "ОТК"]


def test_отгруженные_заказы_за_период_по_дате_отгрузки() -> None:
    plant = make_plant()
    shipped, in_work = launch_order(plant=plant), launch_order(plant=plant)
    now = timezone.now()
    ProductionOrder.objects.filter(id=shipped.id).update(stage=OrderStage.DONE, shipped_at=now)
    today = timezone.localdate()

    result = facade.list_shipped_orders(today - timedelta(days=1), today)

    assert [o.id for o in result] == [shipped.id]
    assert result[0].shipped_at == today
    assert facade.list_shipped_orders(today + timedelta(days=1), today + timedelta(days=9)) == []
    assert in_work.id not in {o.id for o in result}
