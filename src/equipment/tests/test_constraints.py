"""Ограничения БД модуля «Оборудование и ТО»: попытка нарушить → `IntegrityError`
(CLAUDE.md §8 — иначе ограничение существует только на бумаге)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from src.core.org.tests.factories import EmployeeFactory
from src.equipment.models import DownReason, RepairKind, RepairStatus
from src.equipment.tests.factories import (
    EquipmentFactory,
    IdleReasonFactory,
    MaintenanceTypeFactory,
    RepairFactory,
    RepairWorkerFactory,
    RuntimeLogFactory,
)

pytestmark = pytest.mark.django_db


def test_нельзя_завести_два_станка_с_одним_инвентарным_номером() -> None:
    EquipmentFactory.create(inventory_no="ИН-1")
    with pytest.raises(IntegrityError):
        EquipmentFactory.create(inventory_no="ИН-1")


def test_наработка_больше_24_часов_в_сутки_нарушает_constraint() -> None:
    reason = IdleReasonFactory.create()
    with pytest.raises(IntegrityError, match="equipment_runtime_max_24h"):
        RuntimeLogFactory.create(
            run=Decimal("20"), setup=Decimal("2"), idle=Decimal("2.5"), idle_reason=reason
        )


def test_ровно_24_часа_в_сутки_допустимы() -> None:
    reason = IdleReasonFactory.create()
    log = RuntimeLogFactory.create(
        run=Decimal("20"), setup=Decimal("2"), idle=Decimal("2"), idle_reason=reason
    )
    assert log.pk is not None


def test_вторая_запись_наработки_за_те_же_сутки_нарушает_constraint() -> None:
    log = RuntimeLogFactory.create()
    with pytest.raises(IntegrityError, match="equipment_runtime_unique_day"):
        RuntimeLogFactory.create(equipment=log.equipment, date=log.date)


def test_отрицательные_часы_нарушают_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_runtime_non_negative"):
        RuntimeLogFactory.create(run=Decimal("-1"))


def test_простой_без_причины_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_runtime_idle_reason"):
        RuntimeLogFactory.create(idle=Decimal("1"))


def test_отказ_без_причины_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_runtime_down_reason"):
        RuntimeLogFactory.create(down=Decimal("1"))


def test_интервал_то_ноль_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_maintenance_interval_positive"):
        MaintenanceTypeFactory.create(interval_hours=Decimal("0"))


def test_два_вида_то_с_одним_кодом_у_станка_невозможны() -> None:
    mtype = MaintenanceTypeFactory.create(code="ТО-1")
    with pytest.raises(IntegrityError):
        MaintenanceTypeFactory.create(equipment=mtype.equipment, code="ТО-1")


def test_окончание_ремонта_раньше_начала_нарушает_constraint() -> None:
    now = timezone.now()
    with pytest.raises(IntegrityError, match="equipment_repair_finish_after_start"):
        RepairFactory.create(started_at=now, finished_at=now - timedelta(minutes=1))


def test_закрытая_запись_без_окончания_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_repair_done_has_finish"):
        RepairFactory.create(status=RepairStatus.DONE, kind=RepairKind.REPAIR)


def test_закрытая_авария_без_категории_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_repair_failure_category"):
        RepairFactory.create(
            status=RepairStatus.DONE, finished_at=timezone.now(), kind=RepairKind.FAILURE
        )


def test_запись_то_без_вида_то_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_repair_maintenance_type"):
        RepairFactory.create(kind=RepairKind.MAINTENANCE)


def test_вид_то_у_аварии_нарушает_constraint() -> None:
    mtype = MaintenanceTypeFactory.create()
    with pytest.raises(IntegrityError, match="equipment_repair_maintenance_type"):
        RepairFactory.create(
            equipment=mtype.equipment, kind=RepairKind.FAILURE, maintenance_type=mtype
        )


def test_номер_ремонта_уникален() -> None:
    RepairFactory.create(number="АР-0001")
    with pytest.raises(IntegrityError):
        RepairFactory.create(number="АР-0001")


def test_часы_исполнителя_ноль_нарушают_constraint() -> None:
    with pytest.raises(IntegrityError, match="equipment_repair_worker_hours_positive"):
        RepairWorkerFactory.create(hours=Decimal("0"))


def test_исполнитель_дважды_в_одном_ремонте_невозможен() -> None:
    worker = RepairWorkerFactory.create(employee=EmployeeFactory.create())
    with pytest.raises(IntegrityError, match="equipment_repair_worker_unique"):
        RepairWorkerFactory.create(repair=worker.repair, employee=worker.employee)


def test_две_причины_остановки_на_один_вид_ремонта_невозможны() -> None:
    DownReason.objects.get_or_create(repair_kind=RepairKind.REPAIR, defaults={"name": "Ремонт"})
    with pytest.raises(IntegrityError, match="equipment_down_reason_unique_kind"):
        DownReason.objects.create(name="Ремонт-2", repair_kind=RepairKind.REPAIR)
