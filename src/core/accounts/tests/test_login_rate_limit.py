"""Ограничение частоты попыток входа (docs/adr/0030-publikatsiya-v-internet.md, мера 1).

Блокировка по связке «учётная запись + адрес» (`AXES_LOCKOUT_PARAMETERS`) — перебор
с одного IP по разным логинам не блокирует эти логины друг через друга, и наоборот."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate
from django.test import RequestFactory

from src.core.accounts.tests.factories import UserFactory

EMAIL = "ivanov@npk-prod.local"
PASSWORD = "password123!"
IP = "203.0.113.7"


def _attempt(password: str, *, ip: str = IP) -> object:
    request = RequestFactory().post("/api/v1/accounts/login")
    request.META["HTTP_X_FORWARDED_FOR"] = ip
    return authenticate(request, username=EMAIL, password=password)


def test_после_лимита_попыток_даже_верный_пароль_отклоняется(db: None) -> None:
    UserFactory(email=EMAIL, password=PASSWORD)

    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert _attempt("неверный-пароль") is None

    # Лимит исчерпан — верный пароль тоже отклоняется, это и есть блокировка,
    # не совпадение: без django-axes этот же вызов вернул бы пользователя.
    assert _attempt(PASSWORD) is None


def test_до_лимита_верный_пароль_проходит(db: None) -> None:
    UserFactory(email=EMAIL, password=PASSWORD)

    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        assert _attempt("неверный-пароль") is None

    assert _attempt(PASSWORD) is not None


def test_блокировка_по_другому_адресу_не_действует(db: None) -> None:
    """Связка «логин + адрес», не только логин — перебор с одного IP не должен
    запирать тот же логин при входе с другого (например, легитимный вход из офиса,
    пока кто-то перебирает пароль снаружи)."""

    UserFactory(email=EMAIL, password=PASSWORD)

    for _ in range(settings.AXES_FAILURE_LIMIT):
        assert _attempt("неверный-пароль", ip="198.51.100.9") is None

    assert _attempt(PASSWORD, ip="203.0.113.99") is not None
