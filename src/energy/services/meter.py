"""Счётчики (§3.7). Единственное место транзакций для `Meter` (И3)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.energy.exceptions import InvalidParent, MeterCodeTaken
from src.energy.models import EnergyResource, Meter, MeterKind, MeterSource
from src.energy.services.common import as_actor


@dataclass(frozen=True)
class MeterDTO:
    code: str
    name: str
    resource_id: UUID
    kind: MeterKind
    parent_id: UUID | None = None
    equipment_id: UUID | None = None
    source: MeterSource = MeterSource.SCADA
    order: int = 0


def _check_parent(meter_id: UUID | None, data: MeterDTO) -> None:
    """Родитель — того же ресурса; цепочка его предков не проходит через сам счётчик."""

    if data.parent_id is None:
        return
    parent = Meter.objects.filter(id=data.parent_id).first()
    if parent is None or parent.resource_id != data.resource_id:
        raise InvalidParent
    seen: set[UUID] = set()
    current: Meter | None = parent
    while current is not None:
        if current.id == meter_id or current.id in seen:
            raise InvalidParent
        seen.add(current.id)
        current = current.parent


def _apply(meter: Meter, data: MeterDTO) -> None:
    meter.code = data.code.strip()
    meter.name = data.name.strip()
    meter.resource = EnergyResource.objects.get(id=data.resource_id)
    meter.kind = data.kind
    meter.parent_id = data.parent_id
    meter.equipment_id = data.equipment_id
    meter.source = data.source
    meter.order = data.order


def create_meter(data: MeterDTO, *, actor_id: UUID | None) -> Meter:
    with transaction.atomic(), as_actor(actor_id):
        if Meter.objects.filter(code=data.code.strip()).exists():
            raise MeterCodeTaken
        _check_parent(None, data)
        meter = Meter()
        _apply(meter, data)
        meter.save()
    return meter


def update_meter(meter_id: UUID, data: MeterDTO, *, actor_id: UUID | None) -> None:
    with transaction.atomic(), as_actor(actor_id):
        meter = Meter.objects.select_for_update().get(id=meter_id)
        if Meter.objects.filter(code=data.code.strip()).exclude(id=meter_id).exists():
            raise MeterCodeTaken
        if data.resource_id != meter.resource_id and meter.children.exists():
            raise InvalidParent("У счётчика есть дочерние — ресурс сменить нельзя.")
        _check_parent(meter_id, data)
        _apply(meter, data)
        meter.save()
