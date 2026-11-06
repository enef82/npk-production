"""Ограничения БД «Производства»: попытка нарушить → `IntegrityError` (CLAUDE.md §8)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.org.tests.factories import EmployeeFactory
from src.production.models import (
    Operation,
    OperationDependency,
    OperationEarning,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
    ProductionSettings,
    TemplateOperationDependency,
    WorkCenter,
)
from src.production.tests.factories import (
    OperationFactory,
    ProductionOrderFactory,
    TemplateOperationFactory,
    WorkCenterFactory,
)

pytestmark = pytest.mark.django_db


def _violates(action: object) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        action()  # type: ignore[operator]


def test_связь_операции_с_самой_собой_нарушает_constraint() -> None:
    op = OperationFactory.create()
    _violates(lambda: OperationDependency.objects.create(predecessor=op, successor=op))


def test_дублирующая_связь_нарушает_constraint() -> None:
    a = OperationFactory.create()
    b = OperationFactory.create(order=a.order)
    OperationDependency.objects.create(predecessor=a, successor=b)
    _violates(lambda: OperationDependency.objects.create(predecessor=a, successor=b))


def test_связь_операций_разных_заказов_отклоняется_триггером() -> None:
    a = OperationFactory.create()
    b = OperationFactory.create()
    with pytest.raises(IntegrityError, match="одного заказа"), transaction.atomic():
        OperationDependency.objects.create(predecessor=a, successor=b)


def test_связь_операций_разных_шаблонов_отклоняется_триггером() -> None:
    a = TemplateOperationFactory.create()
    b = TemplateOperationFactory.create()
    with pytest.raises(IntegrityError, match="одного шаблона"), transaction.atomic():
        TemplateOperationDependency.objects.create(predecessor=a, successor=b)


def test_прогресс_не_кратный_десяти_нарушает_constraint() -> None:
    op = OperationFactory.create(
        status=OperationStatus.WORK, started_at=timezone.now(), progress=10
    )
    _violates(lambda: Operation.objects.filter(id=op.id).update(progress=15))


def test_ожидающая_операция_с_прогрессом_нарушает_constraint() -> None:
    op = OperationFactory.create()
    _violates(lambda: Operation.objects.filter(id=op.id).update(progress=50))


def test_начатая_операция_без_отметки_начала_нарушает_constraint() -> None:
    op = OperationFactory.create()
    _violates(lambda: Operation.objects.filter(id=op.id).update(status=OperationStatus.WORK))


def test_выполненная_операция_без_визы_нарушает_constraint() -> None:
    op = OperationFactory.create(status=OperationStatus.WORK, started_at=timezone.now())
    _violates(
        lambda: Operation.objects.filter(id=op.id).update(status=OperationStatus.DONE, progress=100)
    )


def test_на_визе_только_полностью_выполненная_операция() -> None:
    op = OperationFactory.create(status=OperationStatus.WORK, started_at=timezone.now())
    _violates(lambda: Operation.objects.filter(id=op.id).update(status=OperationStatus.CHECK))


def test_номер_операции_уникален_в_заказе() -> None:
    op = OperationFactory.create(seq=10)
    _violates(lambda: OperationFactory.create(order=op.order, seq=10))


def test_исполнителей_не_меньше_одного() -> None:
    op = OperationFactory.create()
    _violates(lambda: Operation.objects.filter(id=op.id).update(people=0))


def test_нулевое_освоение_не_записывается() -> None:
    op = OperationFactory.create()
    _violates(
        lambda: OperationEarning.objects.create(
            operation=op, date=timezone.localdate(), hours=Decimal("0")
        )
    )


def test_дата_отгрузки_есть_ровно_у_отгруженного_заказа() -> None:
    order = ProductionOrderFactory.create()
    _violates(lambda: ProductionOrder.objects.filter(id=order.id).update(shipped_at=timezone.now()))
    _violates(lambda: ProductionOrder.objects.filter(id=order.id).update(stage=OrderStage.DONE))


def test_второй_заказ_по_той_же_заявке_нарушает_constraint() -> None:
    inquiry_id = uuid4()
    ProductionOrderFactory.create(inquiry_id=inquiry_id)
    _violates(lambda: ProductionOrderFactory.create(inquiry_id=inquiry_id))


def test_производственный_участок_без_исполнителей_нарушает_constraint() -> None:
    _violates(lambda: WorkCenterFactory.create(capacity=0, is_supply=False))
    WorkCenterFactory.create(capacity=0, is_supply=True)
    assert WorkCenter.objects.filter(capacity=0).count() == 1


def test_настройки_производства_одна_запись() -> None:
    ProductionSettings.objects.create()
    _violates(lambda: ProductionSettings.objects.create(id=uuid4()))


def test_виза_этапа_без_даты_нарушает_constraint() -> None:
    order = ProductionOrderFactory.create()
    _violates(
        lambda: OrderStageApproval.objects.create(
            order=order, stage=OrderStage.LAUNCH, approved_by=EmployeeFactory.create()
        )
    )
