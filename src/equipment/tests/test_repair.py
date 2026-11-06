"""Журнал аварий и ремонтов: статусы (включая запрещённые переходы), закрытие —
событие `equipment.repair_closed` в той же транзакции (И4), простой в наработке,
запись ТО, состояние оборудования."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.events.models import OutboxEvent
from src.core.org.tests.factories import EmployeeFactory
from src.equipment.exceptions import (
    CloseRequirementsNotMet,
    DescriptionRequired,
    DuplicateWorker,
    InvalidTransition,
    MaintenanceTypeMismatch,
    ReferenceNotFound,
)
from src.equipment.exceptions import RepairClosed as RepairClosedError
from src.equipment.models import (
    DownReason,
    Equipment,
    EquipmentStatus,
    MaintenanceRecord,
    Repair,
    RepairKind,
    RepairStatus,
    RuntimeLog,
)
from src.equipment.services.repair import (
    MaintenanceDTO,
    RepairDTO,
    WorkerDTO,
    close_repair,
    create_repair,
    perform_maintenance,
    start_repair,
    update_repair,
)
from src.equipment.tests.factories import (
    DownReasonFactory,
    EquipmentFactory,
    FailureCategoryFactory,
    MaintenanceTypeFactory,
    RuntimeLogFactory,
)

pytestmark = pytest.mark.django_db

EVENT = "equipment.repair_closed"


def _last_weekday() -> datetime:
    day = timezone.localdate() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return timezone.make_aware(datetime.combine(day, time(9, 0)))


def _failure(equipment: Equipment, **overrides: object) -> Repair:
    worker = EmployeeFactory.create()
    data = {
        "kind": RepairKind.FAILURE,
        "started_at": _last_weekday(),
        "description": "Ошибка привода оси",
        "category_id": FailureCategoryFactory.create().id,
        "workers": [WorkerDTO(employee_id=worker.id, hours=Decimal("2.5"))],
    }
    data.update(overrides)
    return create_repair(equipment.id, RepairDTO(**data), actor_id=uuid4())  # type: ignore[arg-type]


def test_регистрация_аварии_даёт_номер_и_переводит_станок_в_ремонт() -> None:
    equipment = EquipmentFactory.create()

    repair = _failure(equipment)

    assert repair.number.startswith("АР-")
    assert repair.status == RepairStatus.OPEN
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.REPAIR


def test_авария_без_описания_не_регистрируется() -> None:
    with pytest.raises(DescriptionRequired):
        _failure(EquipmentFactory.create(), description="  ")


def test_сотрудник_дважды_в_ремонте_не_принимается() -> None:
    worker = EmployeeFactory.create()
    with pytest.raises(DuplicateWorker):
        _failure(
            EquipmentFactory.create(),
            workers=[
                WorkerDTO(employee_id=worker.id, hours=Decimal("1")),
                WorkerDTO(employee_id=worker.id, hours=Decimal("2")),
            ],
        )


def test_вид_то_чужого_станка_не_принимается() -> None:
    foreign = MaintenanceTypeFactory.create()
    with pytest.raises(MaintenanceTypeMismatch):
        _failure(
            EquipmentFactory.create(),
            kind=RepairKind.MAINTENANCE,
            maintenance_type_id=foreign.id,
            category_id=None,
        )


def test_закрытие_публикует_событие_с_часами_исполнителей() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    equipment = EquipmentFactory.create()
    repair = _failure(equipment)
    start_repair(repair.id, actor_id=None)

    close_repair(repair.id, finished_at=repair.started_at + timedelta(hours=3), actor_id=None)

    repair = Repair.objects.get(id=repair.id)
    assert repair.status == RepairStatus.DONE
    event = OutboxEvent.objects.get(event_type=EVENT, aggregate_id=repair.id)
    worker = repair.workers.get()
    assert event.payload == {
        "equipment_id": str(equipment.id),
        "date": timezone.localdate(repair.started_at).isoformat(),
        "number": repair.number,
        "workers": [{"employee_id": str(worker.employee_id), "hours": "2.50"}],
    }
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.RUN


def test_простой_закрытой_аварии_уходит_в_наработку_суток() -> None:
    reason = DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    equipment = EquipmentFactory.create()
    started = _last_weekday()
    RuntimeLogFactory.create(equipment=equipment, date=started.date(), run=Decimal("7"))
    repair = _failure(equipment, started_at=started, finished_at=started + timedelta(hours=2))

    close_repair(repair.id, actor_id=None)

    log = RuntimeLog.objects.get(equipment=equipment, date=started.date())
    assert (log.run, log.down, log.down_reason_id) == (Decimal("5.00"), Decimal("2.00"), reason.id)


def test_откат_закрытия_не_оставляет_события() -> None:
    """Нет причины остановки для вида — закрытие падает целиком: ни статуса, ни события."""

    DownReason.objects.filter(repair_kind=RepairKind.FAILURE).delete()
    equipment = EquipmentFactory.create()
    repair = _failure(equipment, finished_at=_last_weekday() + timedelta(hours=1))

    with pytest.raises(ReferenceNotFound):
        close_repair(repair.id, actor_id=None)

    assert Repair.objects.get(id=repair.id).status == RepairStatus.OPEN
    assert not OutboxEvent.objects.filter(event_type=EVENT).exists()


def test_событие_откатывается_вместе_с_внешней_транзакцией() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    repair = _failure(EquipmentFactory.create(), finished_at=_last_weekday() + timedelta(hours=1))

    with pytest.raises(RuntimeError), transaction.atomic():
        close_repair(repair.id, actor_id=None)
        raise RuntimeError("сбой после закрытия")

    assert Repair.objects.get(id=repair.id).status == RepairStatus.OPEN
    assert not OutboxEvent.objects.filter(event_type=EVENT, aggregate_id=repair.id).exists()


def test_закрыть_без_окончания_нельзя() -> None:
    repair = _failure(EquipmentFactory.create())
    with pytest.raises(CloseRequirementsNotMet, match="окончание"):
        close_repair(repair.id, actor_id=None)


def test_закрыть_без_исполнителей_нельзя() -> None:
    repair = _failure(
        EquipmentFactory.create(), workers=[], finished_at=_last_weekday() + timedelta(hours=1)
    )
    with pytest.raises(CloseRequirementsNotMet, match="исполнителей"):
        close_repair(repair.id, actor_id=None)


def test_закрыть_аварию_без_категории_нельзя() -> None:
    repair = _failure(
        EquipmentFactory.create(),
        category_id=None,
        finished_at=_last_weekday() + timedelta(hours=1),
    )
    with pytest.raises(CloseRequirementsNotMet, match="категорию"):
        close_repair(repair.id, actor_id=None)


def test_повторно_закрыть_и_править_закрытую_запись_нельзя() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    repair = _failure(EquipmentFactory.create(), finished_at=_last_weekday() + timedelta(hours=1))
    close_repair(repair.id, actor_id=None)

    with pytest.raises(RepairClosedError):
        close_repair(repair.id, actor_id=None)
    with pytest.raises(InvalidTransition):
        start_repair(repair.id, actor_id=None)
    with pytest.raises(RepairClosedError):
        update_repair(
            repair.id,
            RepairDTO(kind=RepairKind.FAILURE, started_at=repair.started_at, description="x"),
            actor_id=None,
        )
    assert OutboxEvent.objects.filter(event_type=EVENT, aggregate_id=repair.id).count() == 1


def test_в_ремонт_дважды_перевести_нельзя() -> None:
    repair = _failure(EquipmentFactory.create())
    start_repair(repair.id, actor_id=None)
    with pytest.raises(InvalidTransition):
        start_repair(repair.id, actor_id=None)


def test_проведённое_то_создаёт_запись_с_текущими_моточасами() -> None:
    DownReasonFactory.create(repair_kind=RepairKind.MAINTENANCE)
    equipment = EquipmentFactory.create(operating_hours_initial=Decimal("1000"))
    started = _last_weekday()
    RuntimeLogFactory.create(equipment=equipment, date=started.date(), run=Decimal("8"))
    mtype = MaintenanceTypeFactory.create(equipment=equipment, code="ТО-1")
    master, operator = EmployeeFactory.create(), EmployeeFactory.create()

    repair = perform_maintenance(
        mtype.id,
        MaintenanceDTO(
            started_at=started,
            finished_at=started + timedelta(hours=4),
            workers=[
                WorkerDTO(employee_id=master.id, hours=Decimal("1")),
                WorkerDTO(employee_id=operator.id, hours=Decimal("3")),
            ],
        ),
        actor_id=uuid4(),
    )

    assert repair.status == RepairStatus.DONE
    assert repair.kind == RepairKind.MAINTENANCE
    record = MaintenanceRecord.objects.get(maintenance_type=mtype)
    # 8 ч работы − 4 ч простоя на ТО = 4 ч; моточасы 1000 + 4.
    assert record.at_hours == Decimal("1004.00")
    assert record.date == started.date()
    assert record.performed_by_id == operator.id  # больше всех часов
    assert OutboxEvent.objects.filter(event_type=EVENT, aggregate_id=repair.id).exists()
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.RUN


def test_открытое_то_переводит_станок_на_то_а_авария_важнее() -> None:
    equipment = EquipmentFactory.create()
    mtype = MaintenanceTypeFactory.create(equipment=equipment)
    _failure(equipment, kind=RepairKind.MAINTENANCE, maintenance_type_id=mtype.id, category_id=None)
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.MAINTENANCE

    _failure(equipment)
    assert Equipment.objects.get(id=equipment.id).status == EquipmentStatus.REPAIR
