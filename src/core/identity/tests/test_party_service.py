from uuid import uuid4

import pytest
from django.db import transaction

from src.core.events.models import OutboxEvent
from src.core.identity.events import PartyArchived
from src.core.identity.models import Party, PartyStatus, PartyType
from src.core.identity.services.dedup import DuplicatesFound
from src.core.identity.services.party import PartyCreateDTO, archive_party, create_party
from src.core.identity.tests.factories import PartyFactory


@pytest.mark.django_db
def test_create_party_находит_дубликат_по_инн() -> None:
    существующий = PartyFactory(inn="7701234567", kpp="770101001")
    данные = PartyCreateDTO(inn="7701234567", kpp="770101001", short_name="Другое имя")

    with pytest.raises(DuplicatesFound) as excinfo:
        create_party(данные, actor_id=uuid4())

    найденные = [match.candidate for match in excinfo.value.matches]
    assert найденные == [существующий]  # type: ignore[comparison-overlap]


@pytest.mark.django_db
def test_create_party_находит_похожего_по_названию() -> None:
    PartyFactory(short_name="ООО Ромашка", inn="", kpp="")
    данные = PartyCreateDTO(short_name="Ромашка ООО")

    with pytest.raises(DuplicatesFound) as excinfo:
        create_party(данные, actor_id=uuid4())

    assert excinfo.value.matches[0].reason == "название"


@pytest.mark.django_db
def test_create_party_с_force_создаёт_несмотря_на_дубликаты() -> None:
    # Точное совпадение по ИНН+КПП в БД заблокировано всегда (см. UniqueConstraint) —
    # force имеет смысл только для нечёткого совпадения по названию.
    PartyFactory(short_name="ООО Ромашка", inn="", kpp="")
    данные = PartyCreateDTO(short_name="Ромашка ООО", party_type=PartyType.LEGAL)

    party = create_party(данные, actor_id=uuid4(), force=True)

    assert party.pk is not None
    assert Party.objects.filter(short_name="Ромашка ООО").count() == 1


@pytest.mark.django_db
def test_archive_party_переводит_в_архив_и_публикует_событие() -> None:
    """Прямая проверка публикации, не через реакцию подписчика (`procurement`) —
    если `publish()` вдруг пропадёт из `archive_party`, обработчик в другом модуле
    молча перестанет срабатывать, и тест на его стороне может пройти по случайной
    причине. Здесь событие проверяется само по себе, без посредников."""

    party = PartyFactory()
    party_id = party.id  # type: ignore[attr-defined]

    archive_party(party_id, actor_id=uuid4(), reason="дубль контрагента")

    party.refresh_from_db()  # type: ignore[attr-defined]
    assert party.status == PartyStatus.ARCHIVED

    event = OutboxEvent.objects.get(event_type=PartyArchived.event_type, aggregate_id=party_id)
    assert event.payload == {}


@pytest.mark.django_db(transaction=True)
def test_archive_party_откат_транзакции_не_оставляет_событие() -> None:
    party = PartyFactory()
    party_id = party.id  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError), transaction.atomic():
        archive_party(party_id, actor_id=uuid4(), reason="дубль контрагента")
        raise RuntimeError("симуляция сбоя после archive_party")

    party.refresh_from_db()  # type: ignore[attr-defined]
    assert party.status != PartyStatus.ARCHIVED
    assert not OutboxEvent.objects.filter(
        event_type=PartyArchived.event_type, aggregate_id=party_id
    ).exists()
