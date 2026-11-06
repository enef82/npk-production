"""Pydantic-схемы входа и выхода API модуля «Аналитика».

Имена с префиксом `Analytics…`: django-ninja кладёт схемы в общий `components.schemas`
OpenAPI по имени класса, и они обязаны быть уникальны во всём API (`tests/test_api.py`).
Проценты — `None`, когда базы нет («—» на экране), а не ноль.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Field, Schema

# --- Отсечки ---


class AnalyticsCutoffRowOut(Schema):
    work_center_id: UUID | None = Field(description="None — строка «Итого»")
    name: str
    capacity: Decimal
    planned: Decimal
    earned: Decimal
    worked: Decimal | None
    plan_pct: Decimal | None
    output_pct: Decimal | None
    load_pct: Decimal | None
    checked: int
    defects: int
    defect_pct: Decimal | None


class AnalyticsCutoffWeekOut(Schema):
    week_start: date
    status: str = Field(description="current / open / closed")
    closed_by_name: str
    closed_at: datetime | None
    comment: str
    rows: list[AnalyticsCutoffRowOut]
    total: AnalyticsCutoffRowOut


class AnalyticsCutoffEventOut(Schema):
    action: str
    action_label: str
    actor_name: str
    created_at: datetime
    text: str


class AnalyticsCutoffAbilitiesOut(Schema):
    can_close: bool


class AnalyticsCutoffsOut(Schema):
    current_week: date
    selected_week: date
    weeks: list[AnalyticsCutoffWeekOut]
    events: list[AnalyticsCutoffEventOut]
    abilities: AnalyticsCutoffAbilitiesOut


class AnalyticsWorkedHoursIn(Schema):
    work_center_id: UUID
    hours: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class AnalyticsCloseCutoffIn(Schema):
    week_start: date
    comment: str = ""
    worked: list[AnalyticsWorkedHoursIn] = Field(
        default_factory=list, description="Правка отработанных часов поверх табеля"
    )


class AnalyticsReopenCutoffIn(Schema):
    reason: str = Field(min_length=1)


class AnalyticsCutoffActionOut(Schema):
    week_start: date
    status: str


# --- Загрузка 10 недель ---


class AnalyticsLoadCellOut(Schema):
    firm: Decimal
    tentative: Decimal
    total: Decimal
    pct: Decimal | None


class AnalyticsLoadRowOut(Schema):
    work_center_id: UUID
    name: str
    short_name: str
    capacity: Decimal
    cells: list[AnalyticsLoadCellOut]


class AnalyticsLoadOut(Schema):
    weeks: list[date]
    rows: list[AnalyticsLoadRowOut]


# --- Портфель ---


class AnalyticsMonthAmountsOut(Schema):
    fact: Decimal
    firm: Decimal
    pipe: Decimal
    total: Decimal


class AnalyticsMonthLoadOut(AnalyticsMonthAmountsOut):
    capacity: Decimal
    pct: Decimal | None
    pipe_pct: Decimal | None


class AnalyticsPortfolioCenterOut(Schema):
    work_center_id: UUID
    name: str
    short_name: str
    months: list[AnalyticsMonthLoadOut]


class AnalyticsPortfolioItemOut(Schema):
    id: UUID
    is_order: bool
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    stage: str
    stage_label: str
    month: date
    total: Decimal
    probability_pct: Decimal
    weighted: Decimal
    kind: str = Field(description="fact / firm / pipe")
    estimated: bool


class AnalyticsStageProbabilityOut(Schema):
    stage: str
    label: str
    probability: Decimal


class AnalyticsPortfolioOut(Schema):
    months: list[date]
    current_month: date
    probabilities: list[AnalyticsStageProbabilityOut]
    revenue: list[AnalyticsMonthAmountsOut]
    load: list[AnalyticsMonthLoadOut]
    centers: list[AnalyticsPortfolioCenterOut]
    items: list[AnalyticsPortfolioItemOut]


# --- Сотрудники ---


class AnalyticsEmployeeMonthOut(Schema):
    month: date
    rub: Decimal
    cost: Decimal
    return_ratio: Decimal | None


class AnalyticsEmployeeStatsOut(Schema):
    worked: Decimal
    on_orders: Decimal
    overhead: Decimal
    idle: Decimal
    repair: Decimal
    training: Decimal
    overtime: Decimal
    absent_days: Decimal
    earned: Decimal
    output_pct: Decimal | None = Field(description="Освоено ÷ часы на заказах")
    use_pct: Decimal | None = Field(description="Часы на заказах ÷ отработано")
    productivity_pct: Decimal | None = Field(description="Освоено ÷ отработано")
    checked: Decimal
    defects: Decimal
    operator_defects: Decimal
    defect_pct: Decimal | None
    rub: Decimal
    cost: Decimal
    return_ratio: Decimal | None = Field(description="Рубли выработки ÷ стоимость часов")
    rub_per_hour: Decimal | None
    contribution: Decimal


class AnalyticsEmployeeRowOut(Schema):
    employee_id: UUID
    full_name: str
    position: str
    department_id: UUID
    department_name: str
    work_center_short: str
    hourly_rate: Decimal
    stats: AnalyticsEmployeeStatsOut
    months: list[AnalyticsEmployeeMonthOut]


class AnalyticsDepartmentOut(Schema):
    id: UUID
    name: str


class AnalyticsEmployeesOut(Schema):
    period: str
    date_from: date
    date_to: date
    months: list[date]
    departments: list[AnalyticsDepartmentOut]
    total: AnalyticsEmployeeStatsOut
    unattributed: Decimal
    rows: list[AnalyticsEmployeeRowOut]


class AnalyticsEmployeeWeekOut(Schema):
    week_start: date
    hours: Decimal
    earned: Decimal
    rub: Decimal
    cost: Decimal
    productivity_pct: Decimal | None


class AnalyticsEmployeeOperationOut(Schema):
    operation_id: UUID
    order_id: UUID
    order_number: str
    operation_name: str
    norm_hours: Decimal
    status: str
    hours: Decimal
    earned: Decimal
    rub: Decimal
    output_pct: Decimal | None


class AnalyticsEmployeeCardOut(Schema):
    employee_id: UUID
    full_name: str
    position: str
    department_name: str
    work_center_short: str
    hourly_rate: Decimal
    period: str
    date_from: date
    date_to: date
    stats: AnalyticsEmployeeStatsOut
    weeks: list[AnalyticsEmployeeWeekOut]
    operations: list[AnalyticsEmployeeOperationOut]
