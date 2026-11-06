from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import factory

from src.supply.models import LineCategory, LineKind, PurchaseLine, Supplier, ToolTemplate


class SupplierFactory(factory.django.DjangoModelFactory[Supplier]):
    class Meta:
        model = Supplier

    name = factory.Sequence(lambda n: f"ООО «Поставщик {n}»")


class ToolTemplateFactory(factory.django.DjangoModelFactory[ToolTemplate]):
    class Meta:
        model = ToolTemplate

    work_center_id = factory.LazyFunction(uuid.uuid4)
    category = LineCategory.TOOL
    name = factory.Sequence(lambda n: f"Инструмент {n}")
    quantity = Decimal("1")
    unit = "шт"
    price = Decimal("100")


class PurchaseLineFactory(factory.django.DjangoModelFactory[PurchaseLine]):
    class Meta:
        model = PurchaseLine

    kind = LineKind.MATERIAL
    category = LineCategory.MATERIAL
    name = factory.Sequence(lambda n: f"Позиция {n}")
    quantity = Decimal("2")
    price = Decimal("1000")
    need_date = date(2026, 11, 20)
