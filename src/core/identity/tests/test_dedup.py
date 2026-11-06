import pytest

from src.core.identity.models import PartyStatus
from src.core.identity.services.dedup import find_party_duplicates
from src.core.identity.tests.factories import PartyFactory


@pytest.mark.django_db
def test_поиск_дубликатов_по_инн_совпадает_точно() -> None:
    party = PartyFactory(inn="7701234567", kpp="770101001")

    найдено = find_party_duplicates(inn="7701234567", kpp="770101001")

    assert [match.candidate for match in найдено] == [party]  # type: ignore[comparison-overlap]
    assert найдено[0].reason == "ИНН"


@pytest.mark.django_db
def test_поиск_дубликатов_не_возвращает_архивные() -> None:
    PartyFactory(inn="7701234567", kpp="770101001", status=PartyStatus.ARCHIVED)
    PartyFactory(short_name="Ромашка", status=PartyStatus.ARCHIVED)

    по_инн = find_party_duplicates(inn="7701234567", kpp="770101001")
    по_имени = find_party_duplicates(name="Ромашка")

    assert по_инн == []
    assert по_имени == []
