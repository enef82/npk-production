"""Pydantic-схемы входа и выхода API модуля «Табель»."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

from src.timesheet.models import AllocationSource, PeriodEventKind, PeriodStatus

# --- Справочники ---


class TimesheetWorkerOut(Schema):
    employee_id: UUID
    full_name: str
    personnel_no: str
    department_id: UUID
    department_name: str
    work_center_id: UUID | None


class OrderOptionOut(Schema):
    order_id: UUID
    label: str


class OperationOptionOut(Schema):
    operation_id: UUID
    label: str
    work_center_id: UUID


class TimeCodeOut(Schema):
    id: UUID
    code: str
    name: str
    is_work: bool
    is_allocatable: bool
    cost_multiplier: Decimal


class DepartmentPeriodOut(Schema):
    department_id: UUID
    code: str
    name: str
    head_name: str
    status: PeriodStatus


# --- Период ---


class PeriodAbilitiesOut(Schema):
    can_edit: bool
    can_fill_plan: bool
    can_submit: bool
    can_confirm_manager: bool
    can_approve: bool
    can_return: bool
    can_send: bool
    can_close: bool
    can_reopen: bool


class PeriodOut(Schema):
    department_id: UUID
    month: date
    status: PeriodStatus
    version: int
    abilities: PeriodAbilitiesOut


class ReasonIn(Schema):
    comment: str


class FillResultOut(Schema):
    filled_days: int
    period: PeriodOut


# --- Сетка месяца ---


class GridDayOut(Schema):
    date: date
    is_weekend: bool


class GridCellOut(Schema):
    date: date
    work_hours: Decimal
    overtime_hours: Decimal
    absence_code: str
    is_trip: bool
    has_overhead: bool
    is_missing: bool


class DayHoursOut(Schema):
    date: date
    hours: Decimal


class ObjectLineOut(Schema):
    target: str
    order_id: UUID | None
    order_label: str
    days: list[DayHoursOut]
    total: Decimal


class GridRowOut(Schema):
    employee_id: UUID
    full_name: str
    personnel_no: str
    position: str
    work_center_id: UUID | None
    cells: list[GridCellOut]
    objects: list[ObjectLineOut]
    total: Decimal
    norm: Decimal
    delta: Decimal


class CheckOut(Schema):
    is_blocking: bool
    text: str
    employee_id: UUID | None


class CodeTotalOut(Schema):
    code: str
    name: str
    hours: Decimal


class ObjectTotalOut(Schema):
    target: str
    order_id: UUID | None
    order_label: str
    analytics: str
    hours: Decimal


class MonthGridOut(Schema):
    period: PeriodOut
    department_code: str
    department_name: str
    head_id: UUID | None
    head_name: str
    days: list[GridDayOut]
    norm_hours: Decimal
    rows: list[GridRowOut]
    checks: list[CheckOut]
    by_code: list[CodeTotalOut]
    by_object: list[ObjectTotalOut]


# --- Согласование ---


class ManagerOrderHoursOut(Schema):
    order_id: UUID
    order_label: str
    hours: Decimal


class ManagerVisaOut(Schema):
    manager_id: UUID
    manager_name: str
    orders: list[ManagerOrderHoursOut]
    confirmed: bool
    can_confirm: bool


class PeriodEventOut(Schema):
    kind: PeriodEventKind
    version: int
    actor_name: str
    manager_name: str
    comment: str
    created_at: datetime


class PeriodReviewOut(Schema):
    period: PeriodOut
    managers: list[ManagerVisaOut]
    events: list[PeriodEventOut]


# --- Разноска ---


class AllocationRowIn(Schema):
    time_code: str
    hours: Decimal
    target: str = ""
    order_id: UUID | None = None
    operation_id: UUID | None = None


class AllocationIn(AllocationRowIn):
    employee_id: UUID
    date: date


class AllocationOut(Schema):
    id: UUID
    employee_id: UUID
    date: date
    time_code: str
    time_code_name: str
    is_work: bool
    target: str
    order_id: UUID | None
    order_label: str
    operation_id: UUID | None
    operation_label: str
    hours: Decimal
    source: AllocationSource
    source_ref: str


class DayIn(Schema):
    rows: list[AllocationRowIn]


class PlannedOpOut(Schema):
    operation_id: UUID
    order_id: UUID
    label: str


class DayOut(Schema):
    employee_id: UUID
    full_name: str
    position: str
    department_id: UUID
    department_name: str
    work_center_id: UUID | None
    date: date
    rows: list[AllocationOut]
    total: Decimal
    can_edit: bool
    planned: list[PlannedOpOut]
