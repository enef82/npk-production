from datetime import date

import factory

from src.core.identity.tests.factories import PartyFactory
from src.core.org.models import (
    CostCenter,
    Department,
    Employee,
    EmployeeStatus,
    LegalEntity,
    Position,
    PositionCategory,
    TaxSystem,
)


class LegalEntityFactory(factory.django.DjangoModelFactory[LegalEntity]):
    class Meta:
        model = LegalEntity

    party = factory.SubFactory(PartyFactory)
    print_name = factory.Sequence(lambda n: f"Юрлицо {n}")
    tax_system = TaxSystem.OSN
    is_primary = False


class DepartmentFactory(factory.django.DjangoModelFactory[Department]):
    class Meta:
        model = Department

    name = factory.Sequence(lambda n: f"Подразделение {n}")
    code = factory.Sequence(lambda n: f"dept-{n}")
    legal_entity = factory.SubFactory(LegalEntityFactory)
    parent = None
    head = None


class PositionFactory(factory.django.DjangoModelFactory[Position]):
    class Meta:
        model = Position

    name = factory.Sequence(lambda n: f"Должность {n}")
    category = PositionCategory.SPECIALIST
    grade = ""


class EmployeeFactory(factory.django.DjangoModelFactory[Employee]):
    class Meta:
        model = Employee

    full_name = factory.Sequence(lambda n: f"Сотрудник {n}")
    personnel_number = factory.Sequence(lambda n: f"{n:05d}")
    department = factory.SubFactory(DepartmentFactory)
    position = factory.SubFactory(PositionFactory)
    hire_date = date(2024, 1, 1)
    status = EmployeeStatus.ACTIVE


class CostCenterFactory(factory.django.DjangoModelFactory[CostCenter]):
    class Meta:
        model = CostCenter

    name = factory.Sequence(lambda n: f"ЦФО {n}")
    code = factory.Sequence(lambda n: f"cc-{n}")
    department = None
