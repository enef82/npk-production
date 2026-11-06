"""Query-фильтры отчётных эндпоинтов модуля «Энергоучёт»."""

from __future__ import annotations

from datetime import date

from ninja import Schema


class PeriodFilters(Schema):
    """Период отчёта, сутки включительно; без дат — 28 суток до вчерашних."""

    date_from: date | None = None
    date_to: date | None = None
