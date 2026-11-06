from __future__ import annotations

from datetime import date
from decimal import Decimal

import factory

from src.core.org.tests.factories import EmployeeFactory
from src.production.models import (
    Operation,
    OperationDependency,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
    ProductTemplate,
    TemplateOperation,
    WorkCenter,
    WorkPhase,
)


class WorkCenterFactory(factory.django.DjangoModelFactory[WorkCenter]):
    class Meta:
        model = WorkCenter

    code = factory.Sequence(lambda n: f"wc{n}")
    short_name = factory.Sequence(lambda n: f"У{n}")
    name = factory.Sequence(lambda n: f"Участок {n}")
    hourly_rate = Decimal("1500")
    capacity = 2
    phase = WorkPhase.PROD
    is_supply = False


class ProductTemplateFactory(factory.django.DjangoModelFactory[ProductTemplate]):
    class Meta:
        model = ProductTemplate

    code = factory.Sequence(lambda n: f"Т{n}")
    name = factory.Sequence(lambda n: f"Изделие {n}")


class TemplateOperationFactory(factory.django.DjangoModelFactory[TemplateOperation]):
    class Meta:
        model = TemplateOperation

    template = factory.SubFactory(ProductTemplateFactory)
    seq = factory.Sequence(lambda n: (n + 1) * 10)
    name = factory.Sequence(lambda n: f"Операция шаблона {n}")
    work_center = factory.SubFactory(WorkCenterFactory)
    hours = Decimal("8")


class ProductionOrderFactory(factory.django.DjangoModelFactory[ProductionOrder]):
    class Meta:
        model = ProductionOrder

    number = factory.Sequence(lambda n: f"ПЗ-тест-{n:04d}")
    customer_name = "АО «Заказчик»"
    product_name = "Шкаф управления"
    quantity = Decimal("1")
    manager = factory.SubFactory(EmployeeFactory)
    planned_start = date(2026, 11, 9)
    due_date = date(2026, 12, 31)
    stage = OrderStage.LAUNCH


class OrderStageApprovalFactory(factory.django.DjangoModelFactory[OrderStageApproval]):
    class Meta:
        model = OrderStageApproval

    order = factory.SubFactory(ProductionOrderFactory)
    stage = OrderStage.LAUNCH
    responsible = factory.SubFactory(EmployeeFactory)


class OperationFactory(factory.django.DjangoModelFactory[Operation]):
    class Meta:
        model = Operation

    order = factory.SubFactory(ProductionOrderFactory)
    seq = factory.Sequence(lambda n: (n + 1) * 10)
    name = factory.Sequence(lambda n: f"Операция {n}")
    work_center = factory.SubFactory(WorkCenterFactory)
    hours = Decimal("8")
    people = 1
    responsible = factory.SubFactory(EmployeeFactory)
    status = OperationStatus.WAIT


class OperationDependencyFactory(factory.django.DjangoModelFactory[OperationDependency]):
    class Meta:
        model = OperationDependency

    predecessor = factory.SubFactory(OperationFactory)
    successor = factory.SubFactory(
        OperationFactory, order=factory.SelfAttribute("..predecessor.order")
    )
