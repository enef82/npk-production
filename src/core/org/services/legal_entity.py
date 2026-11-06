"""Создание юрлиц и назначение основной организации. Единственное место транзакций
для LegalEntity."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.core.org.models import LegalEntity, TaxSystem


@dataclass(frozen=True)
class LegalEntityCreateDTO:
    party_id: UUID
    print_name: str
    tax_system: TaxSystem
    default_signatory_id: UUID | None = None


def create_legal_entity(data: LegalEntityCreateDTO) -> LegalEntity:
    with transaction.atomic():
        legal_entity = LegalEntity.objects.create(
            party_id=data.party_id,
            print_name=data.print_name,
            tax_system=data.tax_system,
            default_signatory_id=data.default_signatory_id,
        )

    return legal_entity


def get_or_create_legal_entity(data: LegalEntityCreateDTO) -> LegalEntity:
    """Для идемпотентного сида: `party` — OneToOneField, поэтому по нему естественный ключ."""

    with transaction.atomic():
        legal_entity, _ = LegalEntity.objects.get_or_create(
            party_id=data.party_id,
            defaults={
                "print_name": data.print_name,
                "tax_system": data.tax_system,
                "default_signatory_id": data.default_signatory_id,
            },
        )

    return legal_entity


def set_primary_legal_entity(legal_entity_id: UUID) -> None:
    """Снимает признак `is_primary` со старой основной организации и ставит на новую
    одной транзакцией — иначе порядок операций «поставить, затем снять» ловит
    IntegrityError partial unique constraint `core_org_legalentity_uniq_primary`."""

    with transaction.atomic():
        LegalEntity.objects.filter(is_primary=True).update(is_primary=False)
        LegalEntity.objects.filter(pk=legal_entity_id).update(is_primary=True)
