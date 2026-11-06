"""Этапы заказа с визами (`checkMove` прототипа): разрешённые и запрещённые переходы,
событие и атомарность."""

from __future__ import annotations

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.accounts.tests.factories import UserFactory
from src.core.documents.models import DocumentLink, DocumentType
from src.core.documents.tests.factories import DocumentFactory
from src.core.events.models import OutboxEvent
from src.core.org.tests.factories import EmployeeFactory
from src.production.exceptions import (
    AlreadyApproved,
    ReasonRequired,
    StageRequirementsNotMet,
    StageSkip,
    VisaRequired,
)
from src.production.models import (
    DocumentRelease,
    Operation,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
)
from src.production.selectors import ORDER_ENTITY
from src.production.services.order import approve_order_stage, move_order_stage
from src.production.tests.support import launch_order

pytestmark = pytest.mark.django_db


def _move(order: ProductionOrder, to: OrderStage, **kwargs: object) -> None:
    actor = UserFactory.create()
    move_order_stage(
        order.id,
        to,
        actor_id=actor.id,
        actor_employee_id=kwargs.pop("employee_id", None),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _approve(order: ProductionOrder, stage: OrderStage) -> None:
    approve_order_stage(
        order.id, stage, actor_id=UserFactory.create().id, approver_id=EmployeeFactory.create().id
    )


def _force_done(order: ProductionOrder, *names: str) -> None:
    approver = EmployeeFactory.create()
    Operation.objects.filter(order=order, name__in=names).update(
        status=OperationStatus.DONE,
        progress=100,
        started_at=timezone.now(),
        approved_at=timezone.now(),
        approved_by=approver,
    )


def _attach_kd(order: ProductionOrder) -> None:
    document = DocumentFactory.create(doc_type=DocumentType.objects.get(code="production.kd"))
    DocumentLink.objects.create(document=document, entity_type=ORDER_ENTITY, entity_id=order.id)


def test_вперёд_без_визы_нельзя() -> None:
    order = launch_order()
    with pytest.raises(VisaRequired):
        _move(order, OrderStage.PREP)
    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.LAUNCH


def test_ответственный_переводит_и_виза_ставится_вместе_с_переходом() -> None:
    order = launch_order()
    me = EmployeeFactory.create()
    _move(order, OrderStage.PREP, employee_id=me.id, may_approve=True)

    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.PREP
    visa = OrderStageApproval.objects.get(order=order, stage=OrderStage.LAUNCH)
    assert visa.approved_by_id == me.id
    assert visa.approved_at is not None


def test_перескочить_этап_нельзя() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)
    with pytest.raises(StageSkip):
        _move(order, OrderStage.PROD)


def test_виза_ставится_только_текущему_этапу_и_один_раз() -> None:
    order = launch_order()
    with pytest.raises(StageRequirementsNotMet):
        _approve(order, OrderStage.PREP)
    _approve(order, OrderStage.LAUNCH)
    with pytest.raises(AlreadyApproved):
        _approve(order, OrderStage.LAUNCH)


def test_подготовка_не_закрывается_без_выполненной_подготовки() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)
    _move(order, OrderStage.PREP)
    _approve(order, OrderStage.PREP)
    with pytest.raises(StageRequirementsNotMet, match="КД"):
        _move(order, OrderStage.PROD)


def test_подготовка_не_закрывается_без_кд() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)
    _move(order, OrderStage.PREP)
    _approve(order, OrderStage.PREP)
    _force_done(order, "КД")
    with pytest.raises(StageRequirementsNotMet, match="без КД"):
        _move(order, OrderStage.PROD)

    _attach_kd(order)
    _move(order, OrderStage.PROD)
    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.PROD


def test_полный_проход_до_отгрузки_ставит_дату_отгрузки() -> None:
    order = launch_order()
    _attach_kd(order)
    for current, nxt, done in (
        (OrderStage.LAUNCH, OrderStage.PREP, ()),
        (OrderStage.PREP, OrderStage.PROD, ("КД",)),
        (OrderStage.PROD, OrderStage.QC, ("Сборка",)),
        (OrderStage.QC, OrderStage.DONE, ("ОТК",)),
    ):
        _force_done(order, *done)
        _approve(order, current)
        _move(order, nxt)
    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.DONE
    assert order.shipped_at is not None
    assert DocumentRelease.objects.count() == 0


def test_изготовление_не_закрывается_с_открытыми_операциями() -> None:
    order = launch_order()
    _attach_kd(order)
    _approve(order, OrderStage.LAUNCH)
    _move(order, OrderStage.PREP)
    _force_done(order, "КД")
    _approve(order, OrderStage.PREP)
    _move(order, OrderStage.PROD)
    _approve(order, OrderStage.PROD)
    with pytest.raises(StageRequirementsNotMet, match="Сборка"):
        _move(order, OrderStage.QC)


def test_возврат_требует_причину_и_снимает_визу_целевого_этапа() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)
    _move(order, OrderStage.PREP)
    with pytest.raises(ReasonRequired):
        _move(order, OrderStage.LAUNCH)

    _move(order, OrderStage.LAUNCH, comment="Заказчик меняет ТЗ")

    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.LAUNCH
    visa = OrderStageApproval.objects.get(order=order, stage=OrderStage.LAUNCH)
    assert visa.approved_at is None
    assert order.journal.filter(text__contains="Заказчик меняет ТЗ").exists()


def test_переход_публикует_событие_со_старым_и_новым_этапом() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)
    _move(order, OrderStage.PREP)
    event = OutboxEvent.objects.get(
        event_type="production.order_stage_changed", aggregate_id=order.id
    )
    assert event.payload == {"from_stage": "launch", "to_stage": "prep"}


def test_откат_транзакции_не_оставляет_ни_перехода_ни_события() -> None:
    order = launch_order()
    _approve(order, OrderStage.LAUNCH)

    class Boom(Exception):
        pass

    with pytest.raises(Boom), transaction.atomic():
        _move(order, OrderStage.PREP)
        raise Boom

    order = ProductionOrder.objects.get(id=order.id)
    assert order.stage == OrderStage.LAUNCH
    assert not OutboxEvent.objects.filter(event_type="production.order_stage_changed").exists()
