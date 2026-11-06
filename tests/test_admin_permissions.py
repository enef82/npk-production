"""Регрессия после переноса на unfold: unfold.admin.ModelAdmin — ещё один потомок
ModelAdmin, но модельные права (view_/change_<model>) должны продолжать работать
так же, как до переноса — пользователь без права получает 403, с правом — 200.

Объектные права здесь не проверяются: они не были подключены к админке ни до, ни
после переноса (см. docs/adr/0010-otlozheny-obyektnye-prava-v-admin.md) — проверять
нечего, регрессировать нечему."""

from collections.abc import Callable

import pytest
from django.contrib.auth.models import Permission
from django.db import models
from django.test import Client

from src.core.accounts.models import User
from src.core.accounts.tests.factories import UserFactory
from src.core.documents.tests.factories import DocumentFactory
from src.core.identity.tests.factories import PartyFactory
from src.core.org.tests.factories import EmployeeFactory


def _client_with_perms(*codenames_and_labels: tuple[str, str]) -> Client:
    user: User = UserFactory(is_staff=True, is_superuser=False)  # type: ignore[assignment]
    for codename, app_label in codenames_and_labels:
        user.user_permissions.add(
            Permission.objects.get(codename=codename, content_type__app_label=app_label)
        )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("app_label", "model_name", "codename", "make_object"),
    [
        ("core_identity", "party", "view_party", PartyFactory),
        ("core_org", "employee", "view_employee", EmployeeFactory),
        ("core_documents", "document", "view_document", DocumentFactory),
    ],
)
def test_админка_уважает_модельные_права_после_переноса_на_unfold(
    app_label: str,
    model_name: str,
    codename: str,
    make_object: Callable[[], models.Model],
) -> None:
    obj = make_object()
    changelist_url = f"/admin/{app_label}/{model_name}/"
    change_url = f"/admin/{app_label}/{model_name}/{obj.pk}/change/"

    without_perm = _client_with_perms()
    assert without_perm.get(changelist_url).status_code == 403
    assert without_perm.get(change_url).status_code == 403

    with_perm = _client_with_perms((codename, app_label))
    assert with_perm.get(changelist_url).status_code == 200
    assert with_perm.get(change_url).status_code == 200
