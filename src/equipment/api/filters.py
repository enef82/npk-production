"""Query-фильтры списочных эндпоинтов модуля «Оборудование и ТО»."""

from __future__ import annotations

from uuid import UUID

from ninja import Field, Schema

from src.equipment.models import RepairKind


class RepairFilters(Schema):
    """Фильтры журнала аварий и ремонтов (прототип: 30 / 90 / 180 дней, вид, станок)."""

    days: int = Field(90, ge=1, le=3660)
    kind: RepairKind | None = None
    equipment_id: UUID | None = None
