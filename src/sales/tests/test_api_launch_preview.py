"""Предпросмотр запуска (`launchDialog` прототипа): расчётное окончание, отставание от
срока и критический путь считаются без сохранения плана заявки."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import Client

from src.core.accounts.tests.factories import UserFactory
from src.sales.models import CalcOperation, CalcOperationDependency
from src.sales.tests.factories import CalcOperationFactory, InquiryFactory

pytestmark = pytest.mark.django_db


def _client() -> Client:
    client = Client()
    client.force_login(UserFactory.create())
    return client


def test_предпросмотр_запуска_считает_окончание_и_критический_путь_не_сохраняя_план() -> None:
    inquiry = InquiryFactory.create()
    cut = CalcOperationFactory.create(inquiry=inquiry, name="Раскрой", hours=Decimal("8"))
    weld = CalcOperationFactory.create(inquiry=inquiry, name="Сварка", hours=Decimal("16"))
    CalcOperationFactory.create(inquiry=inquiry, name="Покраска", hours=Decimal("8"))
    CalcOperationDependency.objects.create(predecessor=cut, successor=weld)

    # Суббота сдвигается на понедельник 09.11; Раскрой 1 день + Сварка 2 дня → среда 11.11.
    response = _client().get(
        f"/api/v1/sales/inquiries/{inquiry.id}/launch-preview",
        {"planned_start": "2026-11-07", "due_date": "2026-11-10"},
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["planned_start"] == "2026-11-09"
    assert body["planned_finish"] == "2026-11-11"
    assert body["length"] == 3
    assert body["days_late"] == 1
    assert body["critical_path"] == ["Раскрой", "Сварка"]
    assert not CalcOperation.objects.filter(inquiry=inquiry, planned_start__isnull=False).exists()


def test_предпросмотр_запуска_без_операций_и_несуществующей_заявки() -> None:
    inquiry = InquiryFactory.create()
    client = _client()
    params = {"planned_start": "2026-11-09", "due_date": "2026-12-01"}

    empty = client.get(f"/api/v1/sales/inquiries/{inquiry.id}/launch-preview", params).json()
    assert (empty["planned_finish"], empty["length"], empty["critical_path"]) == (None, 0, [])

    missing = client.get(
        "/api/v1/sales/inquiries/00000000-0000-0000-0000-000000000000/launch-preview", params
    )
    assert missing.status_code == 404
    anonymous = Client().get(f"/api/v1/sales/inquiries/{inquiry.id}/launch-preview", params)
    assert anonymous.status_code == 401
