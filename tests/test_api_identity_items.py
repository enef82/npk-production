"""API номенклатуры (`core.identity`) через HTTP. Расположение — см. докстроку
`tests/test_api_identity_parties.py`: нужен настоящий пользователь из `core.accounts`.
"""

from __future__ import annotations

import pytest
from django.test import Client

from src.core.accounts.tests.factories import UserFactory
from src.core.identity.models import ItemType
from src.core.identity.tests.factories import ItemFactory, UnitOfMeasureFactory


@pytest.mark.django_db
def test_список_номенклатуры_требует_аутентификации() -> None:
    response = Client().get("/api/v1/identity/items")

    assert response.status_code == 401


@pytest.mark.django_db
def test_список_номенклатуры_фильтруется_по_типу() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    ItemFactory(name="Труба", item_type=ItemType.MATERIAL)
    ItemFactory(name="Консультация", item_type=ItemType.SERVICE)

    response = client.get("/api/v1/identity/items", {"item_type": "service"})

    assert response.status_code == 200
    body = response.json()
    assert [i["name"] for i in body["items"]] == ["Консультация"]


@pytest.mark.django_db
def test_список_номенклатуры_отдаёт_код_единицы_измерения_строкой() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    uom = UnitOfMeasureFactory(code="кг")
    ItemFactory(name="Кабель", base_uom=uom)

    response = client.get("/api/v1/identity/items")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["base_uom"] == "кг"


@pytest.mark.django_db
def test_список_номенклатуры_поддерживает_with_total() -> None:
    """Один сквозной тест на with_total для /items — не дублирует всю матрицу из
    tests/test_api_identity_parties.py, только проверяет, что общий `_add_total`
    действительно подключён к этому эндпоинту, а не только к /parties."""

    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    ItemFactory.create_batch(2)

    without = client.get("/api/v1/identity/items").json()
    with_total = client.get("/api/v1/identity/items", {"with_total": "1"}).json()

    assert "total" not in without
    assert with_total["total"] == 2
