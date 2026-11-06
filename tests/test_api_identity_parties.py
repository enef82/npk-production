"""API контрагентов (`core.identity`) целиком — через HTTP, не сервис напрямую.

Живёт на верхнем уровне, а не в src/core/identity/tests: тестам нужен настоящий
залогиненный пользователь (`core.accounts`) и права (`django.contrib.auth.Permission`),
а `core.identity` лежит ниже `core.accounts` в слоевом контракте (`.importlinter`) —
импорт в эту сторону запрещён. См. `tests/test_admin_identity_dedup.py`, тот же приём.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from src.core.accounts.models import User
from src.core.accounts.tests.factories import UserFactory
from src.core.identity.models import Party
from src.core.identity.tests.factories import PartyFactory


def _grant(user: User, codename: str) -> None:
    user.user_permissions.add(
        Permission.objects.get(codename=codename, content_type__app_label="core_identity")
    )


@pytest.mark.django_db
def test_список_контрагентов_требует_аутентификации() -> None:
    response = Client().get("/api/v1/identity/parties")

    assert response.status_code == 401


@pytest.mark.django_db
def test_список_контрагентов_фильтруется_по_поиску() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    PartyFactory(short_name="Ромашка")
    PartyFactory(short_name="Одуванчик")

    response = client.get("/api/v1/identity/parties", {"search": "Ромашка"})

    assert response.status_code == 200
    body = response.json()
    assert [p["short_name"] for p in body["items"]] == ["Ромашка"]


@pytest.mark.django_db
def test_список_контрагентов_обходится_курсором_без_пропусков_и_дублей() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    for i in range(5):
        PartyFactory(short_name=f"Компания {i:03d}")

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params: dict[str, str | int] = {"page_size": 2, "ordering": "short_name"}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/api/v1/identity/parties", params)
        assert response.status_code == 200
        body = response.json()
        seen.extend(p["short_name"] for p in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == [f"Компания {i:03d}" for i in range(5)]


@pytest.mark.django_db
def test_недопустимая_сортировка_возвращает_422() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]

    response = client.get("/api/v1/identity/parties", {"ordering": "мимо-списка"})

    assert response.status_code == 422


@pytest.mark.django_db
def test_карточка_контрагента_404_для_несуществующего() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]

    response = client.get(f"/api/v1/identity/parties/{uuid4()}")

    assert response.status_code == 404


@pytest.mark.django_db
def test_создание_контрагента_без_права_add_party_запрещено() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]

    response = client.post(
        "/api/v1/identity/parties",
        {"short_name": "Новый", "legal_name": "Новый ООО", "inn": "7701234567"},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_создание_контрагента_с_правом_add_party_создаёт_черновик() -> None:
    client = Client()
    user: User = UserFactory()  # type: ignore[assignment]
    _grant(user, "add_party")
    client.force_login(user)

    response = client.post(
        "/api/v1/identity/parties",
        {"short_name": "Новый", "legal_name": "Новый ООО", "inn": "7701234567"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["status"] == "draft"


@pytest.mark.django_db
def test_создание_с_дублирующимся_инн_возвращает_409_с_кандидатами() -> None:
    client = Client()
    user: User = UserFactory()  # type: ignore[assignment]
    _grant(user, "add_party")
    client.force_login(user)
    PartyFactory(inn="7701234567", kpp="", short_name="Существующий")

    response = client.post(
        "/api/v1/identity/parties",
        {"short_name": "Новый", "legal_name": "Новый ООО", "inn": "7701234567"},
        content_type="application/json",
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "duplicates_found"
    assert len(body["details"]) == 1
    assert body["details"][0]["reason"] == "ИНН"


@pytest.mark.django_db
def test_force_без_права_force_create_party_запрещён() -> None:
    client = Client()
    user: User = UserFactory()  # type: ignore[assignment]
    _grant(user, "add_party")
    client.force_login(user)

    response = client.post(
        "/api/v1/identity/parties",
        {"short_name": "Новый", "legal_name": "Новый ООО", "force": True},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_force_создаёт_несмотря_на_похожее_название_для_администратора() -> None:
    """`force=True` обходит только мягкое (нечёткое по названию) совпадение —
    точное совпадение (инн, кпп) у активного контрагента физически невозможно
    (ограничение БД, docs/spec/02-yadro-identichnosti.md §3.1), поэтому здесь
    разные ИНН, но одинаковое short_name — ровно сценарий из спецификации §5.1."""

    client = Client()
    client.force_login(UserFactory(is_superuser=True, is_staff=True))  # type: ignore[arg-type]
    PartyFactory(inn="7701234567", kpp="", short_name="Ромашка")

    response = client.post(
        "/api/v1/identity/parties",
        {
            "short_name": "Ромашка",
            "legal_name": "Ромашка ООО",
            "inn": "7709876543",
            "force": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert Party.objects.filter(short_name="Ромашка").count() == 2


@pytest.mark.django_db
def test_создание_с_пустым_названием_возвращает_422_с_полем() -> None:
    client = Client()
    user: User = UserFactory()  # type: ignore[assignment]
    _grant(user, "add_party")
    client.force_login(user)

    response = client.post(
        "/api/v1/identity/parties",
        {"short_name": "", "legal_name": "Что-то"},
        content_type="application/json",
    )

    assert response.status_code == 422
    body = response.json()
    assert any(err["loc"][-1] == "short_name" for err in body["errors"])


@pytest.mark.django_db
def test_проверка_дубликатов_возвращает_кандидата_по_инн() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    existing = PartyFactory(inn="7701234567", kpp="", short_name="Существующий")

    response = client.get("/api/v1/identity/parties/check-duplicates", {"inn": "7701234567"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(existing.id)  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_без_with_total_поля_total_отсутствуют_в_ответе() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    PartyFactory()

    response = client.get("/api/v1/identity/parties")

    body = response.json()
    assert "total" not in body
    assert "total_cap" not in body


@pytest.mark.django_db
@override_settings(PAGINATION_TOTAL_CAP=2)
def test_with_total_возвращает_точное_число_при_количестве_не_больше_порога() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    PartyFactory.create_batch(2)

    params: dict[str, str | int] = {"with_total": "1", "page_size": 1}
    response = client.get("/api/v1/identity/parties", params)

    body = response.json()
    assert body["total"] == 2
    assert body["total_cap"] == 2


@pytest.mark.django_db
@override_settings(PAGINATION_TOTAL_CAP=2)
def test_with_total_возвращает_null_при_количестве_больше_порога() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    PartyFactory.create_batch(3)

    params: dict[str, str | int] = {"with_total": "1", "page_size": 1}
    response = client.get("/api/v1/identity/parties", params)

    body = response.json()
    assert body["total"] is None
    assert body["total_cap"] == 2


@pytest.mark.django_db
def test_with_total_добавляет_ровно_один_дополнительный_запрос() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    PartyFactory.create_batch(3)

    with CaptureQueriesContext(connection) as without_total:
        response_without = client.get("/api/v1/identity/parties")
    with CaptureQueriesContext(connection) as with_total:
        response_with = client.get("/api/v1/identity/parties", {"with_total": "1"})

    assert response_without.status_code == 200
    assert response_with.status_code == 200
    assert len(with_total.captured_queries) == len(without_total.captured_queries) + 1
