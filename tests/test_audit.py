"""core.audit (django-pghistory): триггеры на уровне БД ловят изменения, которые обычные
библиотеки аудита на сигналах Django пропускают (`bulk_update`/`QuerySet.update()`), и
прикрепляют пользователя запроса к записи истории даже когда изменение сделано из админки."""

from uuid import uuid4

from django.db import transaction
from django.test import Client
from django.urls import reverse

from src.core.accounts.models import User
from src.core.identity.models import (  # type: ignore[attr-defined]
    Party,
    PartyEvent,
    PartyStatus,
)
from src.core.identity.services.party import PartyCreateDTO, create_party
from src.core.identity.tests.factories import PartyFactory
from src.core.numbering.models import Numerator, NumeratorEvent  # type: ignore[attr-defined]
from src.core.numbering.tests.factories import NumeratorFactory
from tests.factories import UserFactory


def test_pghistory_ловит_bulk_update(db: None) -> None:
    party: Party = PartyFactory(status=PartyStatus.ACTIVE)  # type: ignore[assignment]

    Party.objects.filter(id=party.id).update(status=PartyStatus.BLOCKED)

    assert PartyEvent.objects.filter(pgh_obj=party.id, status=PartyStatus.BLOCKED).exists()


def test_pghistory_ловит_изменение_из_админки(client: Client, db: None) -> None:
    администратор: User = UserFactory(  # type: ignore[assignment]
        is_staff=True, is_superuser=True
    )
    client.force_login(администратор)

    нумератор: Numerator = NumeratorFactory(name="До правки")  # type: ignore[assignment]

    url = reverse("admin:core_numbering_numerator_change", args=[нумератор.id])
    response = client.post(
        url,
        {
            "code": нумератор.code,
            "name": "После правки из админки",
            "template": нумератор.template,
            "reset_period": нумератор.reset_period,
            "is_active": "on" if нумератор.is_active else "",
        },
    )
    assert response.status_code == 302

    нумератор.refresh_from_db()
    assert нумератор.name == "После правки из админки"

    событие = (
        NumeratorEvent.objects.filter(pgh_obj=нумератор.id, name="После правки из админки")
        .select_related("pgh_context")
        .latest("pgh_created_at")
    )
    assert событие.pgh_context is not None
    assert событие.pgh_context.metadata.get("user") == str(администратор.id)


def test_актор_доезжает_до_истории_вне_http_запроса(db: None) -> None:
    """`create_party` вызван напрямую из тела теста — как из Celery-задачи или
    management-команды: `pghistory.middleware.HistoryMiddleware` здесь не сработал,
    контекст запроса не открыт. Актор должен попасть в историю всё равно —
    `actor_context()` открывает свой собственный контекст, если родительского ещё нет."""

    actor_id = uuid4()

    party = create_party(PartyCreateDTO(short_name="Актор без HTTP"), actor_id=actor_id)

    событие = (
        PartyEvent.objects.filter(pgh_obj=party.id)
        .select_related("pgh_context")
        .latest("pgh_created_at")
    )
    assert событие.pgh_context is not None
    assert событие.pgh_context.metadata.get("actor_id") == str(actor_id)


def test_история_не_теряется_при_откате_внешней_транзакции(db: None) -> None:
    """`create_party` открывает вложенный `transaction.atomic()` (savepoint) внутри уже
    открытой внешней транзакции этого теста. Запись в `PartyEvent` пишется БД-триггером
    в той же транзакции, что и сама строка `Party` — откат внешней транзакции обязан
    откатить обе согласованно: не должно остаться ни осиротевшей записи истории на
    несуществующий объект, ни наоборот, объекта без записи о своём создании."""

    actor_id = uuid4()

    try:
        with transaction.atomic():
            party = create_party(PartyCreateDTO(short_name="Откат"), actor_id=actor_id)
            party_id = party.id
            raise RuntimeError("имитация сбоя после создания")
    except RuntimeError:
        pass

    assert not Party.objects.filter(id=party_id).exists()
    assert not PartyEvent.objects.filter(pgh_obj=party_id).exists()
