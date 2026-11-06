"""Ограничения БД заявок: попытка нарушить → `IntegrityError` (CLAUDE.md §8)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from src.core.org.tests.factories import EmployeeFactory
from src.sales.models import (
    CalcOperation,
    CalcOperationDependency,
    Inquiry,
    InquiryStage,
    InquiryStageApproval,
    SalesSettings,
)
from src.sales.tests.factories import (
    CalcMaterialFactory,
    CalcOperationFactory,
    InquiryFactory,
    LossReasonFactory,
)

pytestmark = pytest.mark.django_db


def _violates(action: Callable[[], object]) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        action()


def test_запущенная_заявка_без_заказа_нарушает_constraint() -> None:
    _violates(lambda: InquiryFactory.create(stage=InquiryStage.LAUNCHED))


def test_заказ_у_незапущенной_заявки_нарушает_constraint() -> None:
    _violates(lambda: InquiryFactory.create(order_id=uuid4()))


def test_проигранная_заявка_без_причины_нарушает_constraint() -> None:
    _violates(lambda: InquiryFactory.create(stage=InquiryStage.LOST))
    _violates(lambda: InquiryFactory.create(lost_reason=LossReasonFactory.create()))


def test_один_заказ_на_одну_заявку() -> None:
    order_id = uuid4()
    InquiryFactory.create(stage=InquiryStage.LAUNCHED, order_id=order_id)
    _violates(lambda: InquiryFactory.create(stage=InquiryStage.LAUNCHED, order_id=order_id))


def test_отрицательные_проценты_и_нулевое_количество_нарушают_constraint() -> None:
    inquiry = InquiryFactory.create()
    _violates(lambda: Inquiry.objects.filter(id=inquiry.id).update(margin_pct=Decimal("-1")))
    _violates(lambda: Inquiry.objects.filter(id=inquiry.id).update(quantity=Decimal("0")))


def test_отрицательная_цена_материала_нарушает_constraint() -> None:
    _violates(lambda: CalcMaterialFactory.create(price=Decimal("-1")))


def test_номер_операции_уникален_в_калькуляции() -> None:
    op = CalcOperationFactory.create(seq=10)
    _violates(lambda: CalcOperationFactory.create(inquiry=op.inquiry, seq=10))
    _violates(lambda: CalcOperation.objects.filter(id=op.id).update(people=0))


def test_связь_операций_разных_заявок_отклоняется_триггером() -> None:
    a = CalcOperationFactory.create()
    b = CalcOperationFactory.create()
    with pytest.raises(IntegrityError, match="одной заявки"), transaction.atomic():
        CalcOperationDependency.objects.create(predecessor=a, successor=b)
    _violates(lambda: CalcOperationDependency.objects.create(predecessor=a, successor=a))


def test_виза_есть_только_у_этапов_заявки() -> None:
    inquiry = InquiryFactory.create()
    _violates(
        lambda: InquiryStageApproval.objects.create(
            inquiry=inquiry, stage=InquiryStage.LAUNCHED, responsible=EmployeeFactory.create()
        )
    )


def test_настройки_заявок_одна_запись_и_вероятность_до_ста() -> None:
    SalesSettings.objects.create()
    _violates(lambda: SalesSettings.objects.create(id=uuid4()))
    _violates(lambda: SalesSettings.objects.update(prob_calc=Decimal("120")))
