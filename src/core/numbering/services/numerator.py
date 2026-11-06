"""Создание нумераторов. Единственное место транзакций для Numerator."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.core.numbering.models import Numerator, NumeratorResetPeriod
from src.core.numbering.template import validate_numerator_template


@dataclass(frozen=True)
class NumeratorCreateDTO:
    code: str
    name: str
    template: str
    legal_entity_id: UUID | None = None
    reset_period: NumeratorResetPeriod = NumeratorResetPeriod.YEARLY


def create_numerator(data: NumeratorCreateDTO) -> Numerator:
    validate_numerator_template(data.template)

    with transaction.atomic():
        numerator = Numerator.objects.create(
            code=data.code,
            name=data.name,
            template=data.template,
            legal_entity_id=data.legal_entity_id,
            reset_period=data.reset_period,
        )

    return numerator
