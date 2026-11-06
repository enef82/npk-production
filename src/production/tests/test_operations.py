"""Операции заказа: статусы (включая запрещённые), прогресс и освоение, виза,
автостарт, откат, правка плана и связей (прототип `opDialog`, `opVisa`, `autoStart`,
`bindGantt`)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone

from src.core.accounts.tests.factories import UserFactory
from src.core.common.scheduling import add_working_days, next_working_day
from src.core.events.models import OutboxEvent
from src.core.org.tests.factories import EmployeeFactory
from src.production.exceptions import (
    CannotMoveEarlier,
    DependencyCycle,
    InspectionRequired,
    InvalidProgress,
    InvalidTransition,
    OperationNotWaiting,
    OrderNotInWork,
    PeopleOverCapacity,
    PredecessorsNotDone,
    SupplyHasNoProgress,
)
from src.production.models import (
    Operation,
    OperationDependency,
    OperationEarning,
    OperationStatus,
    OrderStage,
    ProductionOrder,
)
from src.production.services import operation as services
from src.production.services.order import shift_order
from src.production.tests.factories import WorkCenterFactory
from src.production.tests.support import launch_order, make_plant

pytestmark = pytest.mark.django_db


def _in_work(order: ProductionOrder) -> ProductionOrder:
    ProductionOrder.objects.filter(id=order.id).update(stage=OrderStage.PREP)
    return ProductionOrder.objects.get(id=order.id)


def _op(order: ProductionOrder, name: str) -> Operation:
    return Operation.objects.select_related("work_center").get(order=order, name=name)


def _actor() -> dict[str, object]:
    return {"actor_id": UserFactory.create().id, "actor_employee_id": EmployeeFactory.create().id}


def _earned(op: Operation) -> Decimal:
    return OperationEarning.objects.filter(operation=op).aggregate(s=Sum("hours"))["s"] or Decimal(
        0
    )


def _status(op: Operation) -> str:
    return str(Operation.objects.get(id=op.id).status)


def _approve(op: Operation) -> None:
    services.approve_operation(
        op.id,
        actor_id=UserFactory.create().id,
        approver_id=op.responsible_id or EmployeeFactory.create().id,
    )


def test_на_этапе_запуска_ход_операций_не_ведётся() -> None:
    order = launch_order()
    with pytest.raises(OrderNotInWork):
        services.set_operation_status(_op(order, "КД").id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]


def test_операцию_нельзя_начать_пока_не_закрыт_предшественник() -> None:
    order = _in_work(launch_order())
    with pytest.raises(PredecessorsNotDone, match="КД"):
        services.set_operation_status(_op(order, "Сборка").id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]


def test_начало_ставит_отметку_и_пишет_журнал() -> None:
    order = _in_work(launch_order())
    services.set_operation_status(_op(order, "КД").id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    op = _op(order, "КД")
    assert op.status == OperationStatus.WORK
    assert op.started_at is not None
    assert op.journal.exists()


def test_прогресс_осваивает_часы_приращением_и_100_уводит_на_визу() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]

    services.set_operation_progress(op.id, 30, **_actor())  # type: ignore[arg-type]
    assert _earned(op) == Decimal("2.40")  # 8 н-ч × 30 %
    services.set_operation_progress(op.id, 50, **_actor())  # type: ignore[arg-type]
    assert _earned(op) == Decimal("4.00")
    assert OperationEarning.objects.filter(operation=op).count() == 2

    services.set_operation_progress(op.id, 100, **_actor())  # type: ignore[arg-type]
    op = _op(order, "КД")
    assert op.status == OperationStatus.CHECK
    assert op.progress == 100
    assert _earned(op) == Decimal("8.00")


def test_прогресс_не_кратный_десяти_отклоняется() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    with pytest.raises(InvalidProgress):
        services.set_operation_progress(op.id, 35, **_actor())  # type: ignore[arg-type]


def test_у_снабжения_нет_процента_и_нет_освоения() -> None:
    supply = WorkCenterFactory.create(is_supply=True, capacity=0)
    plant = make_plant()
    plant.prep = supply
    order = _in_work(launch_order(plant=plant))
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    with pytest.raises(SupplyHasNoProgress):
        services.set_operation_progress(op.id, 50, **_actor())  # type: ignore[arg-type]
    _approve(_op(order, "КД"))
    assert _earned(op) == Decimal("0")


def test_откат_до_ожидания_обнуляет_прогресс_и_сторнирует_освоение() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    services.set_operation_progress(op.id, 60, **_actor())  # type: ignore[arg-type]

    services.set_operation_status(op.id, OperationStatus.WAIT, **_actor())  # type: ignore[arg-type]

    op = _op(order, "КД")
    assert op.status == OperationStatus.WAIT
    assert op.progress == 0
    assert op.started_at is None
    assert _earned(op) == Decimal("0")
    assert OperationEarning.objects.filter(operation=op, hours__lt=0).exists()


def test_выполненной_операция_становится_только_по_визе() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    with pytest.raises(InvalidTransition):
        services.set_operation_status(op.id, OperationStatus.DONE, **_actor())  # type: ignore[arg-type]


def test_виза_не_ожидающей_операции_запрещена() -> None:
    order = _in_work(launch_order())
    with pytest.raises(InvalidTransition):
        _approve(_op(order, "КД"))


def test_виза_закрывает_операцию_осваивает_полностью_и_публикует_событие() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    _approve(op)

    op = _op(order, "КД")
    assert op.status == OperationStatus.DONE
    assert op.progress == 100
    assert op.approved_by_id == op.responsible_id
    assert op.approved_for_id is None
    assert _earned(op) == Decimal("8.00")
    event = OutboxEvent.objects.get(event_type="production.operation_approved", aggregate_id=op.id)
    assert event.payload == {"order_id": str(order.id), "work_center_id": str(op.work_center_id)}


def test_виза_за_ответственного_отмечается() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    chief = EmployeeFactory.create()
    services.approve_operation(op.id, actor_id=UserFactory.create().id, approver_id=chief.id)
    op = _op(order, "КД")
    assert op.approved_by_id == chief.id
    assert op.approved_for_id == op.responsible_id


def test_виза_без_записи_контроля_запрещена_если_у_участка_есть_точка_контроля(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.quality import facade as quality

    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    monkeypatch.setattr(quality, "requires_inspection", lambda work_center_id: True)
    with pytest.raises(InspectionRequired):
        _approve(op)
    monkeypatch.setattr(quality, "has_inspection", lambda operation_id: True)
    _approve(op)
    assert _status(op) == OperationStatus.DONE


def test_виза_предшественника_запускает_готовые_последователи() -> None:
    today = timezone.localdate()
    order = _in_work(launch_order(planned_start=add_working_days(today, -3)))
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    _approve(op)

    assembly = _op(order, "Сборка")
    assert assembly.status == OperationStatus.WORK
    assert assembly.started_by_id is None  # «система»
    assert _status(_op(order, "ОТК")) == OperationStatus.WAIT


def test_исполнителей_не_больше_мощности_участка() -> None:
    order = launch_order()
    op = _op(order, "Сборка")
    with pytest.raises(PeopleOverCapacity):
        services.set_operation_people(op.id, 4, **_actor())  # type: ignore[arg-type]


def test_исполнители_пересчитывают_план() -> None:
    order = launch_order()
    otk_before = _op(order, "ОТК").planned_start
    services.set_operation_people(_op(order, "Сборка").id, 1, **_actor())  # type: ignore[arg-type]
    assert otk_before is not None
    assert _op(order, "ОТК").planned_start == add_working_days(otk_before, 1)


def test_план_начатой_операции_не_правится() -> None:
    order = _in_work(launch_order())
    op = _op(order, "КД")
    services.set_operation_status(op.id, OperationStatus.WORK, **_actor())  # type: ignore[arg-type]
    with pytest.raises(OperationNotWaiting):
        services.set_operation_not_before(op.id, timezone.localdate(), **_actor())  # type: ignore[arg-type]


def test_не_ранее_сдвигает_операцию_и_последователей() -> None:
    order = launch_order()
    target = next_working_day(order.planned_start + timedelta(days=14))
    services.set_operation_not_before(_op(order, "Сборка").id, target, **_actor())  # type: ignore[arg-type]
    assert _op(order, "Сборка").planned_start == target
    assert _op(order, "ОТК").planned_start == add_working_days(target, 1)


def test_перенос_раньше_предшественника_запрещён_с_его_названием() -> None:
    order = launch_order()
    assembly = _op(order, "Сборка")
    with pytest.raises(CannotMoveEarlier, match="«КД»"):
        services.move_operation(assembly.id, order.planned_start, **_actor())  # type: ignore[arg-type]
    assert _op(order, "Сборка").not_before is None


def test_перенос_позже_записывается_как_не_ранее() -> None:
    order = launch_order()
    target = add_working_days(order.planned_start, 5)
    services.move_operation(_op(order, "ОТК").id, target, **_actor())  # type: ignore[arg-type]
    otk = _op(order, "ОТК")
    assert otk.not_before == target
    assert otk.planned_start == target


def test_сдвиг_заказа_двигает_запуск_и_не_ранее_на_рабочие_дни() -> None:
    order = launch_order()
    target = add_working_days(order.planned_start, 5)
    services.set_operation_not_before(_op(order, "ОТК").id, target, **_actor())  # type: ignore[arg-type]
    start = order.planned_start

    shift_order(order.id, 3, actor_id=UserFactory.create().id, actor_employee_id=None)

    order = ProductionOrder.objects.get(id=order.id)
    assert order.planned_start == add_working_days(start, 3)
    assert _op(order, "КД").planned_start == order.planned_start
    assert _op(order, "ОТК").not_before == add_working_days(target, 3)


def test_циклическая_связь_отклоняется() -> None:
    order = launch_order()
    with pytest.raises(DependencyCycle):
        services.set_predecessors(_op(order, "КД").id, [_op(order, "ОТК").id], **_actor())  # type: ignore[arg-type]


def test_предшественники_заменяются_целиком_и_план_пересчитывается() -> None:
    order = launch_order()
    otk = _op(order, "ОТК")
    services.set_predecessors(otk.id, [_op(order, "КД").id], **_actor())  # type: ignore[arg-type]
    assert list(
        OperationDependency.objects.filter(successor=otk).values_list(
            "predecessor__name", flat=True
        )
    ) == ["КД"]
    assert _op(order, "ОТК").planned_start == add_working_days(order.planned_start, 1)
