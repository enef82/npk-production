"""Pydantic-схемы входа и выхода API модуля «Ядро: идентичность»."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Field, Schema

from src.core.identity.models import ItemStatus, ItemType, PartyStatus, PartyType


class PartyListItem(Schema):
    id: UUID
    short_name: str
    inn: str
    party_type: PartyType
    status: PartyStatus
    created_at: datetime


class PartyOut(PartyListItem):
    legal_name: str
    kpp: str
    updated_at: datetime


class PartyProfileOut(Schema):
    title: str
    attributes: dict[str, Any]


class PartyIn(Schema):
    short_name: str = Field(..., min_length=1, max_length=255)
    legal_name: str = Field(..., min_length=1, max_length=512)
    inn: str = Field("", max_length=12)
    kpp: str = Field("", max_length=9)
    party_type: PartyType = PartyType.LEGAL
    force: bool = False


class DuplicateMatchOut(Schema):
    id: UUID
    label: str
    inn: str
    score: str
    reason: str


class ItemListItem(Schema):
    id: UUID
    code: str
    name: str
    item_type: ItemType
    base_uom: str
    status: ItemStatus
    created_at: datetime
