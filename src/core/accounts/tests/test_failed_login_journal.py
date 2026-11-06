import logging

import pytest
from django.contrib.auth import authenticate
from django.test import RequestFactory

from src.core.accounts.tests.factories import UserFactory


@pytest.mark.django_db
def test_неудачный_вход_пишется_в_журнал_с_адресом_из_x_forwarded_for(
    caplog: pytest.LogCaptureFixture,
) -> None:
    UserFactory(email="ivanov@npk-prod.local")
    request = RequestFactory().post("/api/v1/accounts/login")
    request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5"

    with caplog.at_level(logging.WARNING, logger="src.core.accounts.signals"):
        user = authenticate(request, username="ivanov@npk-prod.local", password="неверный-пароль")

    assert user is None
    assert "ivanov@npk-prod.local" in caplog.text
    assert "203.0.113.5" in caplog.text


@pytest.mark.django_db
def test_успешный_вход_ничего_не_пишет_в_журнал(caplog: pytest.LogCaptureFixture) -> None:
    UserFactory(email="petrov@npk-prod.local", password="password123!")

    with caplog.at_level(logging.WARNING, logger="src.core.accounts.signals"):
        user = authenticate(
            RequestFactory().post("/api/v1/accounts/login"),
            username="petrov@npk-prod.local",
            password="password123!",
        )

    assert user is not None
    assert caplog.text == ""
