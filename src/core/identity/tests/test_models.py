import pytest
from django.db import IntegrityError, transaction

from src.core.identity.models import Item, Party, PartyStatus, PartyType
from src.core.identity.tests.factories import ItemFactory, PartyFactory

PARTY_FIELDS = {"id", "inn", "kpp", "legal_name", "short_name", "party_type", "status"}
ITEM_FIELDS = {"id", "code", "name", "item_type", "base_uom", "status"}


@pytest.mark.django_db
def test_нельзя_создать_двух_контрагентов_с_одинаковым_инн_и_кпп() -> None:
    PartyFactory(inn="7701234567", kpp="770101001")

    with pytest.raises(IntegrityError), transaction.atomic():
        PartyFactory(inn="7701234567", kpp="770101001")


@pytest.mark.django_db
def test_архивный_контрагент_не_блокирует_создание_нового_с_тем_же_инн() -> None:
    PartyFactory(inn="7701234567", kpp="770101001", status=PartyStatus.ARCHIVED)

    новый = PartyFactory(inn="7701234567", kpp="770101001", status=PartyStatus.ACTIVE)

    assert новый.pk is not None  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_пустой_инн_не_участвует_в_проверке_уникальности() -> None:
    PartyFactory(inn="", kpp="")
    второй = PartyFactory(inn="", kpp="")

    assert второй.pk is not None  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_кпп_запрещён_для_ип_и_физлица() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        PartyFactory(party_type=PartyType.PERSON, kpp="770101001")


@pytest.mark.django_db
def test_код_номенклатуры_уникален() -> None:
    ItemFactory(code="ITEM-001")

    with pytest.raises(IntegrityError), transaction.atomic():
        ItemFactory(code="ITEM-001")


def test_ядро_party_имеет_ровно_семь_полей() -> None:
    # ._meta.fields — только реальные колонки таблицы. ._meta.get_fields() потянул бы
    # ещё и обратные связи от профилей модулей (например, "procurement_profile"),
    # а профили по спецификации (docs/spec/02-yadro-identichnosti.md, §3.8) в счёт
    # семи полей не идут — это отдельные таблицы, а не колонки Party.
    поля = {f.name for f in Party._meta.fields if f.name not in {"created_at", "updated_at"}}

    assert поля == PARTY_FIELDS


def test_ядро_item_имеет_ровно_шесть_полей() -> None:
    поля = {f.name for f in Item._meta.fields if f.name not in {"created_at", "updated_at"}}

    assert поля == ITEM_FIELDS
