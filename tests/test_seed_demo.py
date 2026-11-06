"""Команда `seed_demo`: сотрудники и пользователи прототипа, демо-данные производства и
заявок; идемпотентна; при DEBUG=False отказывается работать."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from src.core.accounts.models import User
from src.core.org.models import Employee
from src.production.models import (
    Operation,
    OperationEarning,
    OperationStatus,
    OrderJournalEntry,
    OrderStage,
    ProductionOrder,
    ProductTemplate,
    WorkCenter,
)
from src.sales.models import Inquiry, InquiryStage, LossReason

pytestmark = pytest.mark.django_db


def test_seed_demo_заводит_прототип_и_идемпотентна() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_demo")

        counts = (
            Employee.objects.count(),
            ProductionOrder.objects.count(),
            Inquiry.objects.count(),
            OrderJournalEntry.objects.count(),
        )
        call_command("seed_demo")

    assert (
        Employee.objects.count(),
        ProductionOrder.objects.count(),
        Inquiry.objects.count(),
        OrderJournalEntry.objects.count(),
    ) == counts
    assert WorkCenter.objects.count() == 12
    assert ProductTemplate.objects.count() == 8
    assert ProductionOrder.objects.count() == 14
    assert Inquiry.objects.count() == 24
    assert LossReason.objects.count() == 4
    # 19 сотрудников `EMP`, 5 персонажей `PEOPLE` вне `EMP` и энергетик (в прототипе его
    # нет); «00001» — директор из `seed`.
    assert Employee.objects.exclude(personnel_number="00001").count() == 25
    morozov = User.objects.get(email="morozov@npk-prod.local")
    assert morozov.check_password("demo12345")
    assert morozov.groups.filter(name="начальник производства").exists()

    # Заказы на разных этапах, с выполненными и начатыми операциями и освоением.
    stages = set(ProductionOrder.objects.values_list("stage", flat=True))
    assert {OrderStage.LAUNCH, OrderStage.DONE} <= stages
    assert len(stages) >= 4
    assert Operation.objects.filter(status=OperationStatus.DONE).exists()
    assert Operation.objects.filter(status=OperationStatus.WORK).exists()
    assert OperationEarning.objects.exists()
    # Каждая запущенная заявка указывает на свой заказ, и наоборот.
    for inquiry in Inquiry.objects.filter(stage=InquiryStage.LAUNCHED):
        assert inquiry.order_id is not None
        assert ProductionOrder.objects.get(id=inquiry.order_id).inquiry_id == inquiry.id
    assert Inquiry.objects.filter(stage=InquiryStage.LAUNCHED).count() == 14


def test_seed_demo_запрещён_при_debug_false() -> None:
    with override_settings(DEBUG=False), pytest.raises(CommandError):
        call_command("seed_demo")
