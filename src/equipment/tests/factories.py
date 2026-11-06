from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from src.core.org.tests.factories import EmployeeFactory
from src.equipment.models import (
    DownReason,
    Equipment,
    FailureCategory,
    IdleReason,
    MaintenanceRecord,
    MaintenanceType,
    Repair,
    RepairKind,
    RepairStatus,
    RepairWorker,
    RuntimeLog,
)


class IdleReasonFactory(factory.django.DjangoModelFactory[IdleReason]):
    class Meta:
        model = IdleReason
        django_get_or_create = ("name",)

    name = "Нет задания"


class DownReasonFactory(factory.django.DjangoModelFactory[DownReason]):
    """Справочник засевает миграция, а `flush()` transactional-тестов его стирает —
    фабрика достаёт существующую причину по виду или заводит её."""

    class Meta:
        model = DownReason
        django_get_or_create = ("repair_kind",)

    repair_kind = RepairKind.FAILURE
    name = factory.LazyAttribute(lambda o: RepairKind(o.repair_kind).label)


class FailureCategoryFactory(factory.django.DjangoModelFactory[FailureCategory]):
    class Meta:
        model = FailureCategory
        django_get_or_create = ("name",)

    name = "Механика"


class EquipmentFactory(factory.django.DjangoModelFactory[Equipment]):
    class Meta:
        model = Equipment

    inventory_no = factory.Sequence(lambda n: f"ИН-Т{n:04d}")
    name = factory.Sequence(lambda n: f"Станок {n}")
    operating_hours_initial = Decimal("1000")


class RuntimeLogFactory(factory.django.DjangoModelFactory[RuntimeLog]):
    class Meta:
        model = RuntimeLog

    equipment = factory.SubFactory(EquipmentFactory)
    date = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=1))
    run = Decimal("6")
    setup = Decimal("0")
    idle = Decimal("0")
    down = Decimal("0")


class MaintenanceTypeFactory(factory.django.DjangoModelFactory[MaintenanceType]):
    class Meta:
        model = MaintenanceType

    equipment = factory.SubFactory(EquipmentFactory)
    code = factory.Sequence(lambda n: f"ТО-{n}")
    interval_hours = Decimal("250")
    scope = "смазка"


class MaintenanceRecordFactory(factory.django.DjangoModelFactory[MaintenanceRecord]):
    class Meta:
        model = MaintenanceRecord

    maintenance_type = factory.SubFactory(MaintenanceTypeFactory)
    date = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=10))
    at_hours = Decimal("900")


class RepairFactory(factory.django.DjangoModelFactory[Repair]):
    class Meta:
        model = Repair

    number = factory.Sequence(lambda n: f"АР-Т{n:04d}")
    equipment = factory.SubFactory(EquipmentFactory)
    kind = RepairKind.FAILURE
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=3))
    description = "Отказ привода"
    status = RepairStatus.OPEN


class RepairWorkerFactory(factory.django.DjangoModelFactory[RepairWorker]):
    class Meta:
        model = RepairWorker

    repair = factory.SubFactory(RepairFactory)
    employee = factory.SubFactory(EmployeeFactory)
    hours = Decimal("2")
