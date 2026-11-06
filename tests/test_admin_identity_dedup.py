"""Админка контрагентов (`core.identity`) создаёт записи только через `create_party`
(И5), а не через `Party.objects.create()` в обход сервиса — и поэтому умеет показывать
дедупликацию прямо в форме, а не падать в 500.

Живёт на верхнем уровне, а не в src/core/identity/tests: тесту нужен настоящий
залогиненный пользователь (`core.accounts`), а `core.identity` лежит ниже `core.accounts`
в слоевом контракте (`.importlinter`) — импорт в эту сторону запрещён."""

import pytest
from django.test import Client

from src.core.accounts.tests.factories import UserFactory
from src.core.identity.models import Party, PartyType
from src.core.identity.tests.factories import PartyFactory

ADD_URL = "/admin/core_identity/party/add/"


@pytest.fixture
def admin_client_() -> Client:
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))  # type: ignore[arg-type]
    return client


@pytest.mark.django_db
def test_создание_контрагента_в_админке_идёт_через_create_party(admin_client_: Client) -> None:
    response = admin_client_.post(
        ADD_URL,
        {
            "inn": "7701234567",
            "kpp": "770101001",
            "legal_name": 'ООО "Новый контрагент"',
            "short_name": "Новый контрагент",
            "party_type": PartyType.LEGAL,
        },
    )

    assert response.status_code == 302  # редирект на changelist — форма принята
    party = Party.objects.get(short_name="Новый контрагент")
    assert party.status == "draft"  # выставляется create_party, не полем формы


@pytest.mark.django_db
def test_дубликат_по_инн_показывает_ошибку_формы_а_не_500(admin_client_: Client) -> None:
    PartyFactory(inn="7701234567", kpp="770101001", short_name="Существующий")
    count_before = Party.objects.count()

    response = admin_client_.post(
        ADD_URL,
        {
            "inn": "7701234567",
            "kpp": "770101001",
            "legal_name": "Другое юрлицо",
            "short_name": "Другое имя",
            "party_type": PartyType.LEGAL,
        },
    )

    assert response.status_code == 200  # форма перерисована с ошибкой, не редирект
    assert "дубликат" in response.content.decode("utf-8").lower()
    assert Party.objects.count() == count_before


@pytest.mark.django_db
def test_force_create_создаёт_несмотря_на_дубликат_по_названию(admin_client_: Client) -> None:
    PartyFactory(short_name="ООО Ромашка", inn="", kpp="")
    count_before = Party.objects.count()

    response = admin_client_.post(
        ADD_URL,
        {
            "inn": "",
            "kpp": "",
            "legal_name": "Ромашка ООО",
            "short_name": "Ромашка ООО",
            "party_type": PartyType.LEGAL,
            "force_create": "on",
        },
    )

    assert response.status_code == 302
    assert Party.objects.count() == count_before + 1
