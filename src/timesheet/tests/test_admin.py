"""Админка табеля идёт через сервисы: наблюдаемый результат — состояние в БД."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from src.core.accounts.tests.factories import UserFactory
from src.core.org.tests.factories import EmployeeFactory
from src.timesheet.models import TimeCode, WorkerProfile

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_() -> Client:
    client = Client()
    client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
    return client


def test_код_вида_времени_правится_через_сервис(admin_client_: Client) -> None:
    code = TimeCode.objects.get(code="С")
    url = reverse("admin:timesheet_timecode_change", args=[code.pk])
    response = admin_client_.post(
        url,
        {
            "code": "С",
            "name": "Сверхурочная работа",
            "is_work": "on",
            "is_allocatable": "on",
            "cost_multiplier": "1.75",
            "sort_order": "30",
        },
    )
    assert response.status_code == 302
    code.refresh_from_db()
    assert (code.name, code.cost_multiplier) == ("Сверхурочная работа", Decimal("1.75"))


def test_профиль_работника_заводится_через_сервис(admin_client_: Client) -> None:
    employee = EmployeeFactory.create()
    response = admin_client_.post(
        reverse("admin:timesheet_workerprofile_add"),
        {
            "employee": str(employee.id),
            "work_center_id": "",
            "hourly_rate": "1250",
        },
    )
    assert response.status_code == 302
    profile = WorkerProfile.objects.get(employee=employee)
    assert (profile.hourly_rate, profile.work_center_id) == (Decimal("1250.0000"), None)


def test_код_вида_времени_не_удаляется(admin_client_: Client) -> None:
    code = TimeCode.objects.get(code="Я")
    response = admin_client_.post(
        reverse("admin:timesheet_timecode_delete", args=[code.pk]), {"post": "yes"}
    )
    assert response.status_code == 403
    assert TimeCode.objects.filter(pk=code.pk).exists()
