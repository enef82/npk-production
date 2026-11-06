"""Query-фильтры списочных эндпоинтов модуля «Ядро: идентичность»."""

from __future__ import annotations

from typing import Annotated

from ninja import FilterLookup, FilterSchema

from src.core.identity.models import ItemStatus, ItemType, PartyStatus, PartyType


class PartyFilters(FilterSchema):
    search: Annotated[
        str | None,
        FilterLookup(["short_name__icontains", "legal_name__icontains", "inn__icontains"]),
    ] = None
    status: PartyStatus | None = None
    party_type: PartyType | None = None


class ItemFilters(FilterSchema):
    search: Annotated[str | None, FilterLookup(["name__icontains", "code__icontains"])] = None
    item_type: ItemType | None = None
    status: ItemStatus | None = None
