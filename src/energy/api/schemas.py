"""Pydantic-схемы входа и выхода API модуля «Энергоучёт»."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ninja import Field, Schema

from src.energy.models import MeterKind, MeterSource

# --- Ресурсы и тарифы ---


class TariffPeriodOut(Schema):
    valid_from: date
    tariff: Decimal


class ResourceOut(Schema):
    id: UUID
    code: str
    name: str
    unit: str
    tariff: Decimal
    tariff_periods: list[TariffPeriodOut]


class EnergyAbilitiesOut(Schema):
    can_manage_meters: bool
    can_ingest_intervals: bool


class ResourcesOut(Schema):
    items: list[ResourceOut]
    abilities: EnergyAbilitiesOut


class TariffIn(Schema):
    valid_from: date
    tariff: Decimal


# --- Счётчики ---


class MeterIn(Schema):
    code: str
    name: str
    resource_id: UUID
    kind: MeterKind
    parent_id: UUID | None = None
    equipment_id: UUID | None = None
    source: MeterSource = MeterSource.SCADA
    order: int = 0


class MeterOut(Schema):
    id: UUID
    code: str
    name: str
    resource_id: UUID
    resource_code: str
    unit: str
    parent_id: UUID | None
    kind: MeterKind
    equipment_id: UUID | None
    source: MeterSource
    order: int


class ReadingIn(Schema):
    taken_at: datetime
    value: Decimal


class ReadingOut(Schema):
    id: UUID
    taken_at: datetime
    value: Decimal


# --- Приём от SCADA ---


class ScadaEnvelopeIn(Schema):
    """Конверт пакета SCADA. Строки — словари: каждая проверяется отдельно, и плохая
    строка отклоняется с причиной, а не роняет весь пакет."""

    schema_version: str = Field(..., max_length=16)
    source_id: str = Field(..., max_length=64)
    message_id: str = Field(..., min_length=1, max_length=64)
    items: list[dict[str, Any]]


class IngestErrorOut(Schema):
    index: int
    code: str
    message: str


class IngestResultOut(Schema):
    message_id: str
    duplicate: bool
    accepted: int
    rejected: int
    errors: list[IngestErrorOut]


class ScadaMessageOut(Schema):
    message_id: str
    source_id: str
    schema_version: str
    items_total: int
    items_accepted: int
    items_rejected: int
    created_at: datetime


# --- Отчёты ---


class ConsumptionOut(Schema):
    resource_id: UUID
    resource_code: str
    period: date
    quantity: Decimal
    cost: Decimal


class BalanceOut(Schema):
    input: Decimal
    children: Decimal
    loss: Decimal
    loss_pct: Decimal | None


class MeterTreeRowOut(Schema):
    meter_id: UUID
    code: str
    name: str
    parent_id: UUID | None
    level: int
    kind: MeterKind
    source: MeterSource
    quantity: Decimal
    previous_quantity: Decimal
    share_pct: Decimal | None
    cost: Decimal
    balance: BalanceOut | None


class DailyOut(Schema):
    meter_id: UUID
    day: date
    quantity: Decimal


class ProfileOut(Schema):
    meter_id: UUID
    day: date
    unit: str
    values: list[Decimal]
    total: Decimal


class BalanceDayOut(Schema):
    day: date
    balance: BalanceOut


class NodeBalanceOut(Schema):
    meter_id: UUID
    children: list[MeterOut]
    total: BalanceOut
    days: list[BalanceDayOut]


class SpecificOut(Schema):
    meter_id: UUID
    meter_code: str
    equipment_id: UUID
    equipment_name: str
    inventory_no: str
    energy: Decimal
    machine_hours: Decimal
    specific: Decimal | None
    cost: Decimal
