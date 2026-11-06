"""Query-фильтры списочных эндпоинтов модуля «Снабжение и склад»."""

from __future__ import annotations

from uuid import UUID

from ninja import Schema

from src.supply.models import LineCategory, LineKind


class LineFilters(Schema):
    """Реестр строк (`prF` прототипа). `status`: код статуса, `active` — всё, кроме
    выданного в цех, `store` — на складе, пусто — все."""

    status: str = "active"
    order_id: UUID | None = None
    warehouse_only: bool = False
    kind: LineKind | None = None
    category: LineCategory | None = None
    late_only: bool = False
    requisition_no: str = ""
    search: str = ""


class OrderLinesFilters(Schema):
    kind: LineKind = LineKind.MATERIAL
