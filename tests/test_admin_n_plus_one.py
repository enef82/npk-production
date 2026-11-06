"""Регрессия N+1 в списках админки после переноса на unfold. `Party` (контрагенты) —
плоская модель без единого FK, тестировать там нечего; реальный риск — колонки
list_display с FK без `list_select_related`/`select_related`: EmployeeAdmin
(department, position), DocumentAdmin (doc_type),
LegalEntityAdmin (default_signatory).

Число запросов на страницу списка не должно расти вместе с числом строк — это и
есть N+1, а не число запросов само по себе (у changelist есть неустранимый
фиксированный оверхед: сессия, права, фильтры)."""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from src.core.accounts.tests.factories import UserFactory
from src.core.documents.tests.factories import DocumentFactory
from src.core.org.tests.factories import EmployeeFactory, LegalEntityFactory


@pytest.fixture
def admin_client_() -> Client:
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))  # type: ignore[arg-type]
    return client


def _query_count(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200
    return len(ctx.captured_queries)


@pytest.mark.django_db
def test_список_сотрудников_в_админке_не_делает_n_plus_1(admin_client_: Client) -> None:
    EmployeeFactory.create_batch(3)
    few = _query_count(admin_client_, "/admin/core_org/employee/")

    EmployeeFactory.create_batch(20)
    many = _query_count(admin_client_, "/admin/core_org/employee/")

    assert many == few


@pytest.mark.django_db
def test_список_документов_в_админке_не_делает_n_plus_1(admin_client_: Client) -> None:
    DocumentFactory.create_batch(3)
    few = _query_count(admin_client_, "/admin/core_documents/document/")

    DocumentFactory.create_batch(20)
    many = _query_count(admin_client_, "/admin/core_documents/document/")

    assert many == few


@pytest.mark.django_db
def test_список_юрлиц_в_админке_не_делает_n_plus_1(admin_client_: Client) -> None:
    def _make(n: int) -> None:
        for _ in range(n):
            LegalEntityFactory(default_signatory=EmployeeFactory())

    _make(3)
    few = _query_count(admin_client_, "/admin/core_org/legalentity/")

    _make(20)
    many = _query_count(admin_client_, "/admin/core_org/legalentity/")

    assert many == few
