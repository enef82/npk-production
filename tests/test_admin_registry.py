"""Смоук-проверка админки после переноса на unfold: список должен открываться для
каждой зарегистрированной модели, без обхода по одной вручную."""

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from src.core.accounts.tests.factories import UserFactory


@pytest.fixture
def admin_client_() -> Client:
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))  # type: ignore[arg-type]
    return client


@pytest.mark.django_db
def test_админка_открывается_для_всех_зарегистрированных_моделей(admin_client_: Client) -> None:
    for model in admin.site._registry:
        url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
        response = admin_client_.get(url)
        assert response.status_code == 200, f"{model!r}: {url} → {response.status_code}"
