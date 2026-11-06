"""Фасад и демо-данные модуля «Оборудование и ТО»."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.core.events.models import OutboxEvent
from src.core.org.tests.factories import EmployeeFactory
from src.equipment import facade
from src.equipment.models import (
    Equipment,
    EquipmentStatus,
    MaintenanceRecord,
    Repair,
    RepairStatus,
    RuntimeLog,
)
from src.equipment.tests.factories import EquipmentFactory, RuntimeLogFactory

pytestmark = pytest.mark.django_db


def test_наработка_за_период_с_машино_часами() -> None:
    equipment = EquipmentFactory.create()
    yesterday = timezone.localdate() - timedelta(days=1)
    RuntimeLogFactory.create(
        equipment=equipment, date=yesterday, run=Decimal("5"), setup=Decimal("1.5")
    )
    RuntimeLogFactory.create(equipment=equipment, date=yesterday - timedelta(days=40))

    rows = facade.get_runtime(yesterday - timedelta(days=7), yesterday)

    assert len(rows) == 1
    assert rows[0].equipment_id == equipment.id
    assert rows[0].machine_hours == Decimal("6.50")


def test_демо_заводит_десять_станков_прототипа_и_идемпотентно() -> None:
    master = EmployeeFactory.create(full_name="Гусев Иван Дмитриевич")
    facade.seed_demo()
    facade.seed_demo()

    equipment = facade.list_equipment()
    assert len(equipment) == 10
    assert {item.inventory_no for item in equipment} >= {"ИН-0012", "ИН-0051"}
    saw = Equipment.objects.get(inventory_no="ИН-0024")
    assert saw.status == EquipmentStatus.REPAIR
    assert Repair.objects.filter(equipment=saw, status=RepairStatus.IN_WORK).exists()
    assert (
        RuntimeLog.objects.filter(date__lt=timezone.localdate() - timedelta(days=56)).count() == 0
    )
    assert MaintenanceRecord.objects.count() == 17
    # Мастер найден по ФИО прототипа «Гусев И.Д.» — аварии закрыты штатно, с событием.
    closed = Repair.objects.filter(status=RepairStatus.DONE, workers__employee=master).distinct()
    assert closed.exists()
    assert OutboxEvent.objects.filter(event_type="equipment.repair_closed").exists()
