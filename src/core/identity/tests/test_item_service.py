from uuid import uuid4

import pytest

from src.core.identity.models import Item, ItemStatus, ItemType
from src.core.identity.services.dedup import DuplicatesFound, find_item_duplicates
from src.core.identity.services.item import ItemCreateDTO, create_item
from src.core.identity.tests.factories import ItemFactory, UnitOfMeasureFactory


@pytest.mark.django_db
def test_create_item_находит_дубликат_по_коду() -> None:
    существующий = ItemFactory(code="ITEM-001")
    uom = UnitOfMeasureFactory()
    данные = ItemCreateDTO(
        code="ITEM-001",
        name="Другое имя",
        item_type=ItemType.MATERIAL,
        base_uom_id=uom.id,  # type: ignore[attr-defined]
    )

    with pytest.raises(DuplicatesFound) as excinfo:
        create_item(данные, actor_id=uuid4())

    найденные = [match.candidate for match in excinfo.value.matches]
    assert найденные == [существующий]  # type: ignore[comparison-overlap]


@pytest.mark.django_db
def test_create_item_с_force_создаёт_несмотря_на_дубликат_по_названию() -> None:
    ItemFactory(name="Труба стальная", code="ITEM-100")
    uom = UnitOfMeasureFactory()
    данные = ItemCreateDTO(
        code="ITEM-200",
        name="Труба стальная",
        item_type=ItemType.MATERIAL,
        base_uom_id=uom.id,  # type: ignore[attr-defined]
    )

    item = create_item(данные, actor_id=uuid4(), force=True)

    assert item.pk is not None
    assert Item.objects.filter(name="Труба стальная").count() == 2


@pytest.mark.django_db
def test_дедуп_номенклатуры_не_возвращает_архивные() -> None:
    ItemFactory(code="ITEM-001", status=ItemStatus.ARCHIVED)

    assert find_item_duplicates(code="ITEM-001") == []
