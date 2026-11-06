"""Тарифы энергоресурсов (§3.7). Единственное место транзакций для `EnergyResource`
и `TariffPeriod` (И3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.energy.exceptions import InvalidTariff
from src.energy.models import EnergyResource, TariffPeriod
from src.energy.services.common import as_actor


def set_tariff(
    resource_id: UUID, valid_from: date, tariff: Decimal, *, actor_id: UUID | None
) -> None:
    """Тариф с даты (повторный ввод той же даты — исправление). Тариф ресурса —
    действующий на сегодня период; будущий период его не меняет."""

    if tariff < 0:
        raise InvalidTariff
    with transaction.atomic(), as_actor(actor_id):
        resource = EnergyResource.objects.select_for_update().get(id=resource_id)
        TariffPeriod.objects.update_or_create(
            resource=resource, valid_from=valid_from, defaults={"tariff": tariff}
        )
        current = (
            TariffPeriod.objects.filter(resource=resource, valid_from__lte=timezone.localdate())
            .order_by("-valid_from")
            .first()
        )
        if current is not None and resource.tariff != current.tariff:
            resource.tariff = current.tariff
            resource.save(update_fields=["tariff", "updated_at"])
