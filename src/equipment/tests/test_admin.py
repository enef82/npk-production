"""Админка «Оборудования»: запись — через сервисы, права — и разрешение, и запрет."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from src.core.accounts.groups import FOREMAN, PRODUCTION_HEAD
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.equipment.models import Equipment, EquipmentStatus

pytestmark = pytest.mark.django_db

PAYLOAD = {
    "inventory_no": "ИН-0500",
    "name": "Гильотина",
    "control_system": "",
    "connection": "",
    "operating_hours_initial": "100",
    "maintenance_types-TOTAL_FORMS": "0",
    "maintenance_types-INITIAL_FORMS": "0",
}


def _staff(*groups: str) -> Client:
    sync_group_permissions()
    user: User = UserFactory.create(is_staff=True)
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    client = Client()
    client.force_login(user)
    return client


def test_начальник_производства_заводит_станок_через_админку() -> None:
    client = _staff(PRODUCTION_HEAD)

    response = client.post("/admin/equipment/equipment/add/", PAYLOAD)

    assert response.status_code == 302, response.content[:800]
    equipment = Equipment.objects.get(inventory_no="ИН-0500")
    assert equipment.status == EquipmentStatus.RUN


def test_мастер_не_заводит_станок_через_админку() -> None:
    client = _staff(FOREMAN)

    response = client.post("/admin/equipment/equipment/add/", PAYLOAD)

    assert response.status_code == 403
    assert not Equipment.objects.filter(inventory_no="ИН-0500").exists()
