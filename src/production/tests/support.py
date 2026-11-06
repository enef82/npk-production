"""Общие построители тестов «Производства»: заказ с операциями через настоящий сервис
запуска, пользователи с ролями."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.core.common.scheduling import add_working_days
from src.core.org.models import Employee
from src.core.org.tests.factories import EmployeeFactory
from src.production.models import ProductionOrder, WorkCenter, WorkPhase
from src.production.services.order import LaunchData, LaunchOperation, create_order_from_inquiry
from src.production.tests.factories import WorkCenterFactory


def user_with_employee(*groups: str) -> tuple[User, Employee]:
    sync_group_permissions()
    user: User = UserFactory.create()
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    return user, EmployeeFactory.create(user=user)


def client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@dataclass
class Plant:
    """Три участка разных фаз и ответственный за каждый."""

    prep: WorkCenter
    prod: WorkCenter
    qc: WorkCenter


def make_plant() -> Plant:
    return Plant(
        prep=WorkCenterFactory.create(
            phase=WorkPhase.PREP, capacity=1, responsible=EmployeeFactory.create()
        ),
        prod=WorkCenterFactory.create(
            phase=WorkPhase.PROD, capacity=3, responsible=EmployeeFactory.create()
        ),
        qc=WorkCenterFactory.create(
            phase=WorkPhase.QC, capacity=1, responsible=EmployeeFactory.create()
        ),
    )


def launch_order(
    *,
    plant: Plant | None = None,
    actor: User | None = None,
    planned_start: date | None = None,
    due_date: date | None = None,
    manager: Employee | None = None,
    inquiry_id: UUID | None = None,
) -> ProductionOrder:
    """Заказ «КД (8 ч) → Сборка (16 ч, 2 чел.) → ОТК (4 ч)» через `create_order_from_inquiry`."""

    plant = plant or make_plant()
    actor = actor or UserFactory.create()
    today = timezone.localdate()
    planned_start = planned_start or add_working_days(today, 5)
    due_date = due_date or today + timedelta(days=90)
    order_id = create_order_from_inquiry(
        LaunchData(
            inquiry_id=inquiry_id or uuid4(),
            inquiry_number="З-0001",
            customer_id=None,
            customer_name="АО «Заказчик»",
            object_name="Котельная",
            product_name="Шкаф",
            template_id=None,
            quantity=Decimal("1"),
            manager_id=(manager or EmployeeFactory.create()).id,
            planned_start=planned_start,
            due_date=due_date,
            contract_total=Decimal("1000000"),
            labor_cost_planned=Decimal("40000"),
            operations=[
                LaunchOperation(10, "КД", plant.prep.id, Decimal("8"), 1),
                LaunchOperation(20, "Сборка", plant.prod.id, Decimal("16"), 2, None, (0,)),
                LaunchOperation(30, "ОТК", plant.qc.id, Decimal("4"), 1, None, (1,)),
            ],
        ),
        actor_id=actor.id,
    )
    return ProductionOrder.objects.get(id=order_id)
