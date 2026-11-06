"""Query-фильтры списочных эндпоинтов модуля «ОТК и качество»."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from ninja import Field, Schema


class SummaryFilters(Schema):
    """Период сводки — последние N недель, включая текущую (прототип: 4 / 8 / 12)."""

    weeks: int = Field(8, ge=1, le=52)


class RecordFilters(Schema):
    date_from: date | None = None
    date_to: date | None = None
    work_center_id: UUID | None = None
    order_id: UUID | None = None
    cause_id: UUID | None = None
    defects_only: bool = False
    limit: int = Field(200, ge=1, le=1000)
