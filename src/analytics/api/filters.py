"""Query-фильтры эндпоинтов модуля «Аналитика»."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from ninja import Field, Schema

from src.analytics.models import EmployeePeriod


class AnalyticsCutoffFilters(Schema):
    """Окно истории — `weeks` недель по текущую включительно (прототип: 8 прошлых и
    текущая); `week` — выбранная неделя (понедельник), по умолчанию текущая."""

    week: date | None = None
    weeks: int = Field(9, ge=2, le=13)


class AnalyticsEmployeeFilters(Schema):
    period: EmployeePeriod = EmployeePeriod.FOUR_WEEKS
    department_id: UUID | None = None


class AnalyticsEmployeeCardFilters(Schema):
    period: EmployeePeriod = EmployeePeriod.FOUR_WEEKS
