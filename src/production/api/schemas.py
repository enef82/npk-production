"""Pydantic-схемы входа и выхода API модуля «Производство».

Выходные схемы повторяют датаклассы `selectors.py` и добавляют серверные `abilities` —
фронт показывает действия по ним, а не по своему пониманию ролей.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

from src.production.models import JournalKind, OperationStatus, OrderStage

# --- Справочники ---


class WorkCenterOut(Schema):
    id: UUID
    code: str
    short_name: str
    name: str
    hourly_rate: Decimal
    capacity: int
    phase: str
    is_supply: bool
    responsible_id: UUID | None
    responsible_name: str
    is_active: bool
    requires_inspection: bool


class TemplateMaterialOut(Schema):
    name: str
    qty_per_unit: Decimal
    price: Decimal


class TemplateOperationOut(Schema):
    seq: int
    name: str
    work_center_id: UUID
    hours: Decimal
    scales_with_qty: bool
    people: int
    predecessor_indexes: list[int]


class TemplateListItem(Schema):
    id: UUID
    code: str
    name: str
    is_active: bool


class TemplateOut(TemplateListItem):
    materials: list[TemplateMaterialOut]
    operations: list[TemplateOperationOut]


class StageResponsibleOut(Schema):
    stage: OrderStage
    stage_label: str
    responsible_id: UUID | None
    responsible_name: str


class ProductionSettingsOut(Schema):
    stages: list[StageResponsibleOut]


class DocumentKindOut(Schema):
    code: str
    name: str


# --- Доска и карточка заказа ---


class HealthOut(Schema):
    color: str
    status: str
    days: int
    text: str


class StageApprovalOut(Schema):
    stage: OrderStage
    stage_label: str
    responsible_id: UUID | None
    responsible_name: str
    approved_by_id: UUID | None
    approved_by_name: str
    approved_at: datetime | None
    comment: str


class BoardAbilitiesOut(Schema):
    can_move: bool
    can_approve_stage: bool


class OrderCardOut(Schema):
    id: UUID
    number: str
    inquiry_id: UUID | None
    inquiry_number: str
    customer_id: UUID | None
    customer_name: str
    object_name: str
    product_name: str
    quantity: Decimal
    manager_id: UUID
    manager_name: str
    planned_start: date
    planned_finish: date | None
    due_date: date
    stage: OrderStage
    derived_stage: OrderStage
    health: HealthOut
    progress: Decimal
    stage_responsible_id: UUID | None
    stage_responsible_name: str
    stage_approved: bool
    contract_total: Decimal
    operations_total: int
    operations_done: int
    abilities: BoardAbilitiesOut


class OrderAbilitiesOut(Schema):
    can_move: bool
    can_approve_stage: bool
    can_edit: bool
    can_plan: bool
    can_manage_documents: bool
    can_comment: bool


class OrderOut(OrderCardOut):
    template_id: UUID | None
    labor_cost_planned: Decimal
    shipped_at: datetime | None
    created_at: datetime
    approvals: list[StageApprovalOut]
    hours_total: Decimal
    earned_total: Decimal
    has_kd: bool
    order_abilities: OrderAbilitiesOut


class OrderUpdateIn(Schema):
    due_date: date
    manager_id: UUID


class StageMoveIn(Schema):
    to: OrderStage
    comment: str = ""


class StageApproveIn(Schema):
    comment: str = ""


class StageResponsibleIn(Schema):
    responsible_id: UUID


class ReplanIn(Schema):
    planned_start: date | None = None


class ShiftIn(Schema):
    days: int


# --- План, операции, Гант ---


class OperationAbilitiesOut(Schema):
    can_change_status: bool
    can_set_progress: bool
    can_approve: bool
    can_edit_plan: bool
    can_set_responsible: bool


class OperationRowOut(Schema):
    id: UUID
    order_id: UUID
    seq: int
    name: str
    work_center_id: UUID
    work_center_short_name: str
    work_center_name: str
    phase: str
    is_supply: bool
    capacity: int
    hours: Decimal
    people: int
    duration: int
    responsible_id: UUID | None
    responsible_name: str
    not_before: date | None
    planned_start: date | None
    planned_finish: date | None
    status: OperationStatus
    progress: int
    earned_hours: Decimal
    started_at: datetime | None
    approved_at: datetime | None
    approved_by_name: str
    approved_for_name: str
    predecessor_ids: list[UUID]
    slack: int | None
    is_critical: bool
    violates_dependency: bool
    requires_inspection: bool
    abilities: OperationAbilitiesOut


class ScheduleOut(Schema):
    order_id: UUID
    planned_start: date
    planned_finish: date | None
    due_date: date
    length: int
    critical_path: list[UUID]
    has_violations: bool
    operations: list[OperationRowOut]


class GanttOperationOut(Schema):
    id: UUID
    seq: int
    name: str
    work_center_id: UUID
    work_center_short_name: str
    is_supply: bool
    status: OperationStatus
    progress: int
    responsible_name: str
    planned_start: date | None
    planned_finish: date | None
    predecessor_ids: list[UUID]
    is_critical: bool
    violates_dependency: bool


class GanttOrderOut(Schema):
    id: UUID
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    stage: OrderStage
    due_date: date
    planned_start: date
    planned_finish: date | None
    health: HealthOut
    can_plan: bool
    operations: list[GanttOperationOut]


class OperationUpdateIn(Schema):
    """Правка плана операции: передаются только меняемые поля. `not_before: null` —
    снять ограничение."""

    people: int | None = None
    not_before: date | None = None
    responsible_id: UUID | None = None


class OperationStatusIn(Schema):
    status: OperationStatus


class OperationProgressIn(Schema):
    progress: int


class OperationApproveIn(Schema):
    comment: str = ""


class OperationMoveIn(Schema):
    start: date


class PredecessorsIn(Schema):
    predecessor_ids: list[UUID]


class OperationLinkOut(Schema):
    id: UUID
    seq: int
    name: str
    status: OperationStatus
    planned_start: date | None
    planned_finish: date | None


class DocumentOut(Schema):
    document_id: UUID
    name: str
    doc_type_code: str
    doc_type_name: str
    version: int
    size_bytes: int
    uploaded_at: datetime
    operation_id: UUID | None
    approved_by_name: str
    approved_at: datetime | None


class JournalEntryOut(Schema):
    id: UUID
    created_at: datetime
    kind: JournalKind
    kind_label: str
    stage: str
    operation_id: UUID | None
    operation_label: str
    author_id: UUID | None
    author_name: str
    text: str


class OperationCardOut(Schema):
    operation: OperationRowOut
    order: OrderCardOut
    predecessors: list[OperationLinkOut]
    successors: list[OperationLinkOut]
    documents: list[DocumentOut]
    journal: list[JournalEntryOut]
    has_inspection: bool


class CommentIn(Schema):
    text: str
    operation_id: UUID | None = None


class CreatedOut(Schema):
    id: UUID


class VisaItemOut(Schema):
    kind: str
    order_id: UUID
    order_number: str
    product_name: str
    customer_name: str
    quantity: Decimal
    due_date: date
    health: HealthOut
    stage: OrderStage
    operation_id: UUID | None
    operation_name: str
    operation_status: str
    text: str
