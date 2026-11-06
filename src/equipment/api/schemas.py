"""Pydantic-схемы входа и выхода API модуля «Оборудование и ТО»."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

from src.equipment.models import (
    EquipmentStatus,
    MaintenanceState,
    RepairKind,
    RepairStatus,
    RuntimeSource,
)

# --- Справочники ---


class ReferenceItemOut(Schema):
    id: UUID
    name: str


class DownReasonOut(ReferenceItemOut):
    repair_kind: RepairKind | None


class ReferenceOut(Schema):
    idle_reasons: list[ReferenceItemOut]
    down_reasons: list[DownReasonOut]
    failure_categories: list[ReferenceItemOut]


# --- Оборудование ---


class EquipmentIn(Schema):
    inventory_no: str
    name: str
    work_center_id: UUID | None = None
    control_system: str = ""
    connection: str = ""
    operating_hours_initial: Decimal = Decimal("0")


class StatusIn(Schema):
    status: EquipmentStatus


class WeekOut(Schema):
    week_start: date
    run: Decimal
    setup: Decimal
    idle: Decimal
    down: Decimal
    days: int
    utilization: Decimal


class MaintenanceStateOut(Schema):
    maintenance_type_id: UUID
    code: str
    interval_hours: Decimal
    scope: str
    last_date: date | None
    last_at_hours: Decimal | None
    next_at_hours: Decimal
    hours_left: Decimal
    due_date: date
    state: MaintenanceState


class EquipmentAbilitiesOut(Schema):
    """Серверные способности текущего пользователя — фронт показывает кнопки по ним."""

    can_edit: bool
    can_set_status: bool
    can_log_runtime: bool
    can_register_repair: bool
    can_manage_maintenance: bool


class EquipmentListItem(Schema):
    id: UUID
    inventory_no: str
    name: str
    work_center_id: UUID | None
    control_system: str
    connection: str
    status: EquipmentStatus
    operating_hours: Decimal
    week: WeekOut
    nearest_maintenance: MaintenanceStateOut | None


class RuntimeIn(Schema):
    date: date
    run: Decimal = Decimal("0")
    setup: Decimal = Decimal("0")
    idle: Decimal = Decimal("0")
    down: Decimal = Decimal("0")
    idle_reason_id: UUID | None = None
    down_reason_id: UUID | None = None


class RuntimeOut(Schema):
    id: UUID
    date: date
    run: Decimal
    setup: Decimal
    idle: Decimal
    down: Decimal
    idle_reason_id: UUID | None
    idle_reason_name: str
    down_reason_id: UUID | None
    down_reason_name: str
    source: RuntimeSource


class RepairListItem(Schema):
    id: UUID
    number: str
    equipment_id: UUID
    equipment_name: str
    equipment_inventory_no: str
    kind: RepairKind
    maintenance_type_id: UUID | None
    category_id: UUID | None
    category_name: str
    started_at: datetime
    finished_at: datetime | None
    downtime_hours: Decimal
    labor_hours: Decimal
    description: str
    fix: str
    status: RepairStatus


class EquipmentOut(Schema):
    id: UUID
    inventory_no: str
    name: str
    work_center_id: UUID | None
    control_system: str
    connection: str
    status: EquipmentStatus
    operating_hours_initial: Decimal
    operating_hours: Decimal
    weeks: list[WeekOut]
    maintenance: list[MaintenanceStateOut]
    recent_runtime: list[RuntimeOut]
    recent_repairs: list[RepairListItem]
    abilities: EquipmentAbilitiesOut


# --- Сводка экрана ---


class KpiOut(Schema):
    equipment_count: int
    utilization: Decimal
    idle_and_down_hours: Decimal
    maintenance_overdue: int
    maintenance_soon: int


class MatrixRowOut(Schema):
    equipment_id: UUID
    name: str
    weeks: list[WeekOut]


class ParetoOut(Schema):
    reason: str
    is_down: bool
    hours: Decimal


class MaintenancePlanOut(Schema):
    equipment_id: UUID
    equipment_name: str
    maintenance: MaintenanceStateOut


class DashboardAbilitiesOut(Schema):
    can_create_equipment: bool
    can_register_repair: bool


class DashboardOut(Schema):
    week_start: date
    weeks: list[date]
    kpi: KpiOut
    matrix: list[MatrixRowOut]
    pareto: list[ParetoOut]
    maintenance_plan: list[MaintenancePlanOut]
    abilities: DashboardAbilitiesOut


# --- Виды ТО ---


class MaintenanceTypeIn(Schema):
    code: str
    interval_hours: Decimal
    scope: str = ""


class WorkerIn(Schema):
    employee_id: UUID
    hours: Decimal


class PerformMaintenanceIn(Schema):
    started_at: datetime
    finished_at: datetime
    workers: list[WorkerIn]
    comment: str = ""


# --- Аварии и ремонты ---


class RepairIn(Schema):
    kind: RepairKind
    started_at: datetime
    description: str
    finished_at: datetime | None = None
    maintenance_type_id: UUID | None = None
    category_id: UUID | None = None
    alarm_code: str = ""
    fix: str = ""
    parts: str = ""
    workers: list[WorkerIn] = []


class RepairCreateIn(RepairIn):
    equipment_id: UUID


class RepairCloseIn(Schema):
    finished_at: datetime | None = None


class WorkerOut(Schema):
    employee_id: UUID
    employee_name: str
    hours: Decimal


class RepairAbilitiesOut(Schema):
    can_edit: bool
    can_start: bool
    can_close: bool


class RepairOut(RepairListItem):
    alarm_code: str
    parts: str
    maintenance_type_code: str
    workers: list[WorkerOut]
    created_at: datetime
    abilities: RepairAbilitiesOut


class CategoryDowntimeOut(Schema):
    category: str
    hours: Decimal


class EquipmentFailuresOut(Schema):
    equipment_id: UUID
    equipment_name: str
    failures: int


class RepairsSummaryOut(Schema):
    failures: int
    failure_downtime: Decimal
    labor_hours: Decimal
    mttr: Decimal
    mtbf: Decimal | None
    downtime_by_category: list[CategoryDowntimeOut]
    failures_by_equipment: list[EquipmentFailuresOut]


class RepairJournalOut(Schema):
    items: list[RepairListItem]
    summary: RepairsSummaryOut
    can_register: bool
