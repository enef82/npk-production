"""Создание, изменение и архивирование номенклатуры. Единственное место транзакций для Item."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.core.identity.models import Item, ItemStatus, ItemType
from src.core.identity.services.dedup import DuplicatesFound, find_item_duplicates


@dataclass(frozen=True)
class ItemCreateDTO:
    code: str
    name: str
    item_type: ItemType
    base_uom_id: UUID


@dataclass(frozen=True)
class ItemUpdateDTO:
    name: str | None = None
    item_type: ItemType | None = None
    base_uom_id: UUID | None = None


def create_item(data: ItemCreateDTO, *, actor_id: UUID, force: bool = False) -> Item:
    if not force:
        duplicates = find_item_duplicates(code=data.code, name=data.name)
        if duplicates:
            raise DuplicatesFound(duplicates)

    with transaction.atomic(), actor_context(actor_id):
        item = Item.objects.create(
            code=data.code,
            name=data.name,
            item_type=data.item_type,
            base_uom_id=data.base_uom_id,
            status=ItemStatus.DRAFT,
        )

    return item


def update_item(item_id: UUID, data: ItemUpdateDTO, *, actor_id: UUID) -> Item:
    with transaction.atomic(), actor_context(actor_id):
        item = Item.objects.select_for_update().get(id=item_id)
        if data.name is not None:
            item.name = data.name
        if data.item_type is not None:
            item.item_type = data.item_type
        if data.base_uom_id is not None:
            item.base_uom_id = data.base_uom_id
        item.save()

    return item


def archive_item(item_id: UUID, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        item = Item.objects.select_for_update().get(id=item_id)
        item.status = ItemStatus.ARCHIVED
        item.save(update_fields=["status", "updated_at"])
