import factory

from src.core.identity.models import (
    AttributeSchema,
    Item,
    ItemStatus,
    ItemType,
    Party,
    PartyStatus,
    PartyType,
    UnitOfMeasure,
)


class UnitOfMeasureFactory(factory.django.DjangoModelFactory[UnitOfMeasure]):
    class Meta:
        model = UnitOfMeasure
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"uom{n}")
    name = "Штука"
    okei_code = "796"
    is_active = True


class PartyFactory(factory.django.DjangoModelFactory[Party]):
    class Meta:
        model = Party

    inn = factory.Sequence(lambda n: str(1000000000 + n))
    kpp = ""
    legal_name = factory.Sequence(lambda n: f"ООО «Компания {n}»")
    short_name = factory.Sequence(lambda n: f"Компания {n}")
    party_type = PartyType.LEGAL
    status = PartyStatus.ACTIVE


class ItemFactory(factory.django.DjangoModelFactory[Item]):
    class Meta:
        model = Item

    code = factory.Sequence(lambda n: f"item-{n}")
    name = factory.Sequence(lambda n: f"Позиция {n}")
    item_type = ItemType.MATERIAL
    base_uom = factory.SubFactory(UnitOfMeasureFactory)
    status = ItemStatus.ACTIVE


class AttributeSchemaFactory(factory.django.DjangoModelFactory[AttributeSchema]):
    class Meta:
        model = AttributeSchema

    app_label = factory.Sequence(lambda n: f"module{n}")
    category = "default"
    schema = factory.LazyFunction(dict)
    is_active = True
