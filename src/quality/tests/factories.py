from __future__ import annotations

import uuid
from datetime import date

import factory

from src.core.org.tests.factories import EmployeeFactory
from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord


class InspectionPointFactory(factory.django.DjangoModelFactory[InspectionPoint]):
    class Meta:
        model = InspectionPoint

    work_center_id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Точка контроля {n}")
    is_final = False


class DefectTypeFactory(factory.django.DjangoModelFactory[DefectType]):
    class Meta:
        model = DefectType

    inspection_point = factory.SubFactory(InspectionPointFactory)
    name = factory.Sequence(lambda n: f"Дефект {n}")


class DefectCauseFactory(factory.django.DjangoModelFactory[DefectCause]):
    class Meta:
        model = DefectCause

    name = factory.Sequence(lambda n: f"Причина {n}")


class InspectionRecordFactory(factory.django.DjangoModelFactory[InspectionRecord]):
    class Meta:
        model = InspectionRecord

    operation_id = factory.LazyFunction(uuid.uuid4)
    order_id = factory.LazyFunction(uuid.uuid4)
    work_center_id = factory.LazyFunction(uuid.uuid4)
    date = date(2026, 11, 4)
    inspector = factory.SubFactory(EmployeeFactory)
    checked = 10
    rework = 0
    scrap = 0
