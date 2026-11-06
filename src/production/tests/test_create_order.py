"""Заказ из заявки: операции со связями, визы этапов, план, событие, идемпотентность."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.core.common.scheduling import add_working_days
from src.core.events.models import OutboxEvent
from src.production.models import (
    JournalKind,
    Operation,
    OperationDependency,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
)
from src.production.tests.support import launch_order, make_plant

pytestmark = pytest.mark.django_db


def test_запуск_создаёт_заказ_с_операциями_связями_и_планом() -> None:
    order = launch_order()

    assert order.number.startswith("ПЗ-")
    assert order.stage == OrderStage.LAUNCH
    ops = list(Operation.objects.filter(order=order).order_by("seq"))
    assert [op.name for op in ops] == ["КД", "Сборка", "ОТК"]
    assert all(op.status == OperationStatus.WAIT for op in ops)
    assert OperationDependency.objects.filter(successor__order=order).count() == 2
    # КД — 1 день, Сборка — 16 ч / (8 × 2) = 1 день, ОТК — 1 день.
    assert ops[0].planned_start == order.planned_start
    assert ops[1].planned_start == add_working_days(order.planned_start, 1)
    assert ops[2].planned_start == add_working_days(order.planned_start, 2)
    assert ops[1].responsible_id == ops[1].work_center.responsible_id
    assert set(
        OrderStageApproval.objects.filter(order=order).values_list("stage", flat=True)
    ) == set(OrderStage.values)
    assert order.journal.filter(kind=JournalKind.STAGE).exists()


def test_запуск_публикует_order_launched() -> None:
    order = launch_order()
    event = OutboxEvent.objects.get(event_type="production.order_launched", aggregate_id=order.id)
    assert event.payload["inquiry_id"] == str(order.inquiry_id)
    assert event.payload["planned_start"] == order.planned_start.isoformat()


def test_повторный_запуск_той_же_заявки_возвращает_тот_же_заказ() -> None:
    plant = make_plant()
    inquiry_id = uuid4()
    first = launch_order(plant=plant, inquiry_id=inquiry_id)
    second = launch_order(plant=plant, inquiry_id=inquiry_id)

    assert first.id == second.id
    assert ProductionOrder.objects.filter(inquiry_id=inquiry_id).count() == 1
