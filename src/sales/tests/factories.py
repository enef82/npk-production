from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import factory

from src.core.org.tests.factories import EmployeeFactory
from src.sales.models import (
    CalcMaterial,
    CalcOperation,
    Inquiry,
    InquiryStage,
    LossReason,
)


class InquiryFactory(factory.django.DjangoModelFactory[Inquiry]):
    class Meta:
        model = Inquiry

    number = factory.Sequence(lambda n: f"З-т{n:04d}")
    customer_id = factory.LazyFunction(uuid4)
    customer_name = "АО «Заказчик»"
    object_name = "Котельная"
    product_name = "Шкаф управления"
    quantity = Decimal("1")
    due_date = date(2026, 12, 31)
    manager = factory.SubFactory(EmployeeFactory)
    stage = InquiryStage.NEW


class LossReasonFactory(factory.django.DjangoModelFactory[LossReason]):
    class Meta:
        model = LossReason

    name = factory.Sequence(lambda n: f"Причина {n}")


class CalcMaterialFactory(factory.django.DjangoModelFactory[CalcMaterial]):
    class Meta:
        model = CalcMaterial

    inquiry = factory.SubFactory(InquiryFactory)
    name = "Корпус"
    quantity = Decimal("1")
    price = Decimal("1000")


class CalcOperationFactory(factory.django.DjangoModelFactory[CalcOperation]):
    class Meta:
        model = CalcOperation

    inquiry = factory.SubFactory(InquiryFactory)
    seq = factory.Sequence(lambda n: (n + 1) * 10)
    name = "Сборка"
    work_center_id = factory.LazyFunction(uuid4)
    hours = Decimal("8")
