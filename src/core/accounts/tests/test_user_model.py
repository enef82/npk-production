import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from src.core.accounts.models import User


def test_используется_кастомная_модель_пользователя() -> None:
    assert settings.AUTH_USER_MODEL == "core_accounts.User"
    assert get_user_model() is User


def test_модель_пользователя_аутентифицируется_по_email_без_username() -> None:
    assert User.USERNAME_FIELD == "email"
    assert not hasattr(User, "username")


@pytest.mark.django_db
def test_email_пользователя_уникален() -> None:
    User.objects.create_user(email="дубль@npk-prod.local", password="pass12345")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="дубль@npk-prod.local", password="pass12345")
