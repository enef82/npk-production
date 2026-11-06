"""Создание, изменение и архивирование контрагентов. Единственное место транзакций для Party."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.core.events.publisher import publish
from src.core.identity.events import PartyArchived
from src.core.identity.models import Party, PartyStatus, PartyType
from src.core.identity.services.dedup import DuplicatesFound, find_party_duplicates


@dataclass(frozen=True)
class PartyCreateDTO:
    inn: str = ""
    kpp: str = ""
    legal_name: str = ""
    short_name: str = ""
    party_type: PartyType = PartyType.LEGAL


@dataclass(frozen=True)
class PartyUpdateDTO:
    legal_name: str | None = None
    short_name: str | None = None
    party_type: PartyType | None = None


def create_party(data: PartyCreateDTO, *, actor_id: UUID, force: bool = False) -> Party:
    if not force:
        duplicates = find_party_duplicates(inn=data.inn, kpp=data.kpp, name=data.short_name)
        if duplicates:
            raise DuplicatesFound(duplicates)

    with transaction.atomic(), actor_context(actor_id):
        party = Party.objects.create(
            inn=data.inn,
            kpp=data.kpp,
            legal_name=data.legal_name,
            short_name=data.short_name,
            party_type=data.party_type,
            status=PartyStatus.DRAFT,
        )

    return party


def update_party(party_id: UUID, data: PartyUpdateDTO, *, actor_id: UUID) -> Party:
    with transaction.atomic(), actor_context(actor_id):
        party = Party.objects.select_for_update().get(id=party_id)
        if data.legal_name is not None:
            party.legal_name = data.legal_name
        if data.short_name is not None:
            party.short_name = data.short_name
        if data.party_type is not None:
            party.party_type = data.party_type
        party.save()

    return party


def archive_party(party_id: UUID, *, actor_id: UUID, reason: str) -> None:
    """`reason` — не поле модели (в `Party` намеренно нет `archive_reason`, ровно семь
    полей, docs/spec/02-yadro-identichnosti.md §2 — не расширять), а метаданные записи
    истории: почему объект архивирован остаётся в аудите, а не разрастает live-схему."""

    with transaction.atomic(), actor_context(actor_id, reason=reason):
        party = Party.objects.select_for_update().get(id=party_id)
        party.status = PartyStatus.ARCHIVED
        party.save(update_fields=["status", "updated_at"])
        publish(PartyArchived(aggregate_id=party_id))
