"""Публичный интерфейс модуля «Ядро: идентичность» для других модулей."""

from __future__ import annotations

from src.core.identity.models import PartyStatus, PartyType
from src.core.identity.selectors import (
    PartyBrief,
    get_item,
    get_parties_brief,
    get_party,
    get_party_360,
)
from src.core.identity.services.dedup import (
    DuplicateMatch,
    DuplicatesFound,
    find_item_duplicates,
    find_party_duplicates,
)
from src.core.identity.services.item import ItemCreateDTO, archive_item, create_item
from src.core.identity.services.party import PartyCreateDTO, archive_party, create_party
from src.core.identity.services.profiles import get_or_create_profile, update_profile_attributes

__all__ = [
    "DuplicateMatch",
    "DuplicatesFound",
    "ItemCreateDTO",
    "PartyBrief",
    "PartyCreateDTO",
    "PartyStatus",
    "PartyType",
    "archive_item",
    "archive_party",
    "create_item",
    "create_party",
    "find_item_duplicates",
    "find_party_duplicates",
    "get_item",
    "get_or_create_profile",
    "get_parties_brief",
    "get_party",
    "get_party_360",
    "update_profile_attributes",
]
