"""API входа/выхода (`core.accounts`) через HTTP: сессия, роли, обработка ошибок."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from src.core.accounts.models import User
from src.core.accounts.tests.factories import UserFactory


@pytest.mark.django_db
def test_вход_с_верными_данными_создаёт_сессию() -> None:
    client = Client()
    user = UserFactory()

    response = client.post(
        "/api/v1/accounts/login",
        {"email": user.email, "password": "password123!"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["email"] == user.email

    me = client.get("/api/v1/accounts/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email


@pytest.mark.django_db
def test_вход_без_csrf_токена_отклоняется() -> None:
    """`/login` — `auth=None`, поэтому обычная cookie-based CSRF-проверка django-ninja
    (`SessionAuth.authenticate` → `check_csrf`) для него сама по себе не выполняется —
    её вызывает явно `_enforce_csrf` внутри `login_view`. Без этого вызова межсайтовая
    форма могла бы тихо залогинить жертву под чужой учётной записью (login CSRF)."""

    client = Client(enforce_csrf_checks=True)
    user = UserFactory()

    response = client.post(
        "/api/v1/accounts/login",
        {"email": user.email, "password": "password123!"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert client.get("/api/v1/accounts/me").status_code == 401


@pytest.mark.django_db
def test_вход_с_верным_csrf_токеном_проходит() -> None:
    client = Client(enforce_csrf_checks=True)
    user = UserFactory()

    csrf_response = client.get("/api/v1/accounts/csrf")
    assert csrf_response.status_code == 200
    csrf_token = client.cookies["csrftoken"].value

    response = client.post(
        "/api/v1/accounts/login",
        {"email": user.email, "password": "password123!"},
        content_type="application/json",
        headers={"X-CSRFToken": csrf_token},
    )

    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_вход_с_неверным_паролем_отклоняется() -> None:
    client = Client()
    user = UserFactory()

    response = client.post(
        "/api/v1/accounts/login",
        {"email": user.email, "password": "неверный"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_вход_с_несуществующим_email_отклоняется_тем_же_сообщением() -> None:
    response = Client().post(
        "/api/v1/accounts/login",
        {"email": "nobody@npk-prod.local", "password": "что-угодно"},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_выход_завершает_сессию() -> None:
    client = Client()
    client.force_login(UserFactory())  # type: ignore[arg-type]
    assert client.get("/api/v1/accounts/me").status_code == 200

    logout_response = client.post("/api/v1/accounts/logout")
    assert logout_response.status_code == 200

    assert client.get("/api/v1/accounts/me").status_code == 401


@pytest.mark.django_db
def test_me_без_аутентификации_возвращает_401() -> None:
    response = Client().get("/api/v1/accounts/me")

    assert response.status_code == 401


@pytest.mark.django_db
def test_me_возвращает_роли_пользователя() -> None:
    client = Client()
    user: User = UserFactory()  # type: ignore[assignment]
    group, _ = Group.objects.get_or_create(name="снабженец")
    user.groups.add(group)
    client.force_login(user)

    response = client.get("/api/v1/accounts/me")

    assert response.status_code == 200
    assert response.json()["roles"] == ["снабженец"]
