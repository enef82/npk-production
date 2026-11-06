"""Обработчик `equipment.repair_closed`: часы ремонта → разноска «ремонт и ТО» с
вытеснением накладных и простоя (`repToTimesheet`), идемпотентность по (номер ремонта,
сотрудник), уведомление начальнику производства, если период закрыт для правки."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import Group
from django.db import transaction

from src.core.accounts.groups import PRODUCTION_HEAD
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.core.events.models import OutboxEvent
from src.core.events.publisher import publish
from src.core.events.services.dispatch import dispatch_batch
from src.core.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationTemplate,
)
from src.timesheet.handlers import apply_repair_hours_to_timesheet
from src.timesheet.models import AllocationSource, PeriodStatus, TimeCode, WorkAllocation
from src.timesheet.tests.factories import TimesheetPeriodFactory, WorkAllocationFactory
from src.timesheet.tests.support import RepairClosedForTest, worker

pytestmark = pytest.mark.django_db

DAY = date(2026, 9, 8)


def _publish(number: str, workers: list[tuple[UUID, str]], day: date = DAY) -> OutboxEvent:
    with transaction.atomic():
        return publish(
            RepairClosedForTest(
                aggregate_id=uuid4(),
                date=day,
                number=number,
                workers=[{"employee_id": e, "hours": h} for e, h in workers],
            )
        )


def _day(employee_id: UUID) -> list[tuple[str, Any, Decimal, str, str]]:
    return [
        (a.target, a.order_id, a.hours, a.source, a.source_ref)
        for a in WorkAllocation.objects.filter(employee_id=employee_id, date=DAY).order_by(
            "created_at", "id"
        )
    ]


def test_payload_события_v1_с_часами_строкой() -> None:
    profile = worker()
    event = _publish("АР-0007", [(profile.employee_id, "3.5")])
    assert event.payload == {
        "date": "2026-09-08",
        "number": "АР-0007",
        "workers": [{"employee_id": str(profile.employee_id), "hours": "3.5"}],
        "equipment_id": event.payload["equipment_id"],
    }


def test_часы_ремонта_вытесняют_накладные_и_простой_затем_заказ() -> None:
    profile = worker()
    order = uuid4()
    WorkAllocationFactory.create(
        employee=profile.employee, date=DAY, target="order", order_id=order, hours=Decimal("5")
    )
    WorkAllocationFactory.create(
        employee=profile.employee, date=DAY, target="overhead", hours=Decimal("2")
    )
    WorkAllocationFactory.create(
        employee=profile.employee, date=DAY, target="idle", hours=Decimal("1")
    )

    _publish("АР-0007", [(profile.employee_id, "4")])
    dispatch_batch()

    assert _day(profile.employee_id) == [
        ("order", order, Decimal("4.00"), "manual", ""),
        ("repair", None, Decimal("4.00"), AllocationSource.REPAIR, "АР-0007"),
    ]
    assert OutboxEvent.objects.get(payload__number="АР-0007").processed_at is not None


def test_ремонт_в_пустой_день_просто_добавляет_часы_а_отпуск_не_вытесняет() -> None:
    profile = worker()
    vacation = worker(profile.employee.department)
    WorkAllocationFactory.create(
        employee=vacation.employee, date=DAY, target="", time_code=TimeCode.objects.get(code="ОТ")
    )

    _publish("АР-0008", [(profile.employee_id, "2"), (vacation.employee_id, "1")])
    dispatch_batch()

    assert _day(profile.employee_id) == [("repair", None, Decimal("2.00"), "repair", "АР-0008")]
    assert [r[0] for r in _day(vacation.employee_id)] == ["", "repair"]


def test_повторная_доставка_не_удваивает_часы() -> None:
    profile = worker()
    WorkAllocationFactory.create(employee=profile.employee, date=DAY, hours=Decimal("8"))
    event = _publish("АР-0009", [(profile.employee_id, "3")])

    apply_repair_hours_to_timesheet(event)
    apply_repair_hours_to_timesheet(event)

    assert _day(profile.employee_id) == [
        ("overhead", None, Decimal("5.00"), "manual", ""),
        ("repair", None, Decimal("3.00"), "repair", "АР-0009"),
    ]


def test_закрытый_период_не_трогается_и_начальник_производства_уведомлён() -> None:
    # Шаблон засевает миграция; здесь — восстановить после `flush()` и упростить текст.
    NotificationTemplate.objects.update_or_create(
        code="timesheet.repair_hours_locked",
        channel=NotificationChannel.IN_APP,
        defaults={"body_template": "{{ number }}: {{ employees }}"},
    )
    sync_group_permissions()
    head = UserFactory.create()
    head.groups.add(Group.objects.get(name=PRODUCTION_HEAD))
    bystander = UserFactory.create()
    locked = worker(full_name="Комаров В.В.")
    open_ = worker()
    TimesheetPeriodFactory.create(
        department=locked.employee.department, status=PeriodStatus.APPROVED
    )
    WorkAllocationFactory.create(employee=locked.employee, date=DAY)

    _publish("АР-0010", [(locked.employee_id, "3"), (open_.employee_id, "3")])
    dispatch_batch()

    assert _day(locked.employee_id) == [("overhead", None, Decimal("8.00"), "manual", "")]
    assert [r[0] for r in _day(open_.employee_id)] == ["repair"]
    notes = Notification.objects.filter(code="timesheet.repair_hours_locked")
    assert [(n.user_id, n.body) for n in notes] == [(head.id, "АР-0010: Комаров В.В.")]
    assert not Notification.objects.filter(user=bystander).exists()


def test_неизвестный_сотрудник_и_нулевые_часы_пропускаются() -> None:
    profile = worker()
    event = _publish("АР-0011", [(uuid4(), "3"), (profile.employee_id, "0")])
    apply_repair_hours_to_timesheet(event)
    assert not WorkAllocation.objects.exists()


def test_откат_транзакции_публикации_не_оставляет_события() -> None:
    profile = worker()
    with pytest.raises(RuntimeError), transaction.atomic():
        publish(
            RepairClosedForTest(
                aggregate_id=uuid4(),
                date=DAY,
                number="АР-0012",
                workers=[{"employee_id": profile.employee_id, "hours": "1"}],
            )
        )
        raise RuntimeError
    assert not OutboxEvent.objects.filter(payload__number="АР-0012").exists()
    dispatch_batch()
    assert not WorkAllocation.objects.exists()
