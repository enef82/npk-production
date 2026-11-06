"""Pydantic-схемы входа и выхода API модуля «Заявки и калькуляция»."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

from src.sales.models import InquiryStage


class InquiryHealthOut(Schema):
    color: str
    status: str
    days: int
    text: str


class InquiryAbilitiesOut(Schema):
    can_edit: bool
    can_edit_calculation: bool
    can_move: bool
    can_approve_stage: bool
    can_launch: bool
    can_lose: bool


class InquiryCardOut(Schema):
    id: UUID
    number: str
    customer_id: UUID
    customer_name: str
    object_name: str
    template_id: UUID | None
    product_name: str
    quantity: Decimal
    due_date: date
    manager_id: UUID
    manager_name: str
    stage: InquiryStage
    health: InquiryHealthOut
    total: Decimal
    probability: Decimal
    stage_responsible_id: UUID | None
    stage_responsible_name: str
    stage_approved: bool
    planned_start: date | None
    planned_finish: date | None
    has_calc: bool
    has_plan: bool
    order_id: UUID | None
    abilities: InquiryAbilitiesOut


class InquiryStageApprovalOut(Schema):
    stage: InquiryStage
    stage_label: str
    responsible_id: UUID | None
    responsible_name: str
    approved_by_id: UUID | None
    approved_by_name: str
    approved_at: datetime | None
    comment: str


class MaterialOut(Schema):
    id: UUID
    name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal


class CalcOperationOut(Schema):
    id: UUID
    seq: int
    name: str
    work_center_id: UUID
    work_center_short_name: str
    work_center_name: str
    is_supply: bool
    capacity: int
    rate: Decimal
    hours: Decimal
    people: int
    duration: int
    not_before: date | None
    planned_start: date | None
    planned_finish: date | None
    predecessor_ids: list[UUID]
    slack: int | None
    is_critical: bool


class TotalsOut(Schema):
    materials: Decimal
    labor: Decimal
    hours: Decimal
    overhead: Decimal
    cost: Decimal
    price: Decimal
    vat: Decimal
    total: Decimal
    profit: Decimal


class InquiryOut(InquiryCardOut):
    overhead_pct: Decimal
    margin_pct: Decimal
    vat_pct: Decimal
    lost_reason_id: UUID | None
    lost_reason_name: str
    lost_comment: str
    created_at: datetime
    approvals: list[InquiryStageApprovalOut]
    materials: list[MaterialOut]
    operations: list[CalcOperationOut]
    totals: TotalsOut
    plan_length: int
    critical_path: list[UUID]


class NewCustomerIn(Schema):
    short_name: str
    inn: str = ""


class InquiryCreateIn(Schema):
    """Заказчик — выбранный контрагент (`customer_id`) или новый (`new_customer`):
    при похожем на существующего ответ 409 `duplicates_found` с кандидатами."""

    customer_id: UUID | None = None
    new_customer: NewCustomerIn | None = None
    object_name: str
    template_id: UUID | None = None
    product_name: str = ""
    quantity: Decimal
    due_date: date
    manager_id: UUID | None = None


class InquiryUpdateIn(Schema):
    object_name: str
    product_name: str
    template_id: UUID | None = None
    quantity: Decimal
    due_date: date
    manager_id: UUID
    overhead_pct: Decimal
    margin_pct: Decimal
    vat_pct: Decimal


class FillFromTemplateIn(Schema):
    template_id: UUID | None = None


class MaterialIn(Schema):
    name: str
    quantity: Decimal
    price: Decimal


class CalcOperationIn(Schema):
    name: str
    work_center_id: UUID
    hours: Decimal
    people: int = 1
    not_before: date | None = None


class CalcPredecessorsIn(Schema):
    predecessor_ids: list[UUID]


class PlanIn(Schema):
    planned_start: date | None = None


class InquiryStageMoveIn(Schema):
    to: InquiryStage
    comment: str = ""


class InquiryStageApproveIn(Schema):
    comment: str = ""


class InquiryStageResponsibleIn(Schema):
    responsible_id: UUID


class LaunchIn(Schema):
    planned_start: date
    due_date: date


class LaunchOut(Schema):
    inquiry_id: UUID
    order_id: UUID
    warnings: list[str]


class LaunchPreviewOut(Schema):
    planned_start: date
    planned_finish: date | None
    length: int
    days_late: int
    critical_path: list[str]


class LoseIn(Schema):
    reason_id: UUID
    comment: str = ""


class LossReasonOut(Schema):
    id: UUID
    name: str


class SalesSettingsOut(Schema):
    economist_id: UUID | None
    economist_name: str
    prob_new: Decimal
    prob_calc: Decimal
    prob_approval: Decimal


class InquiryVisaItemOut(Schema):
    inquiry_id: UUID
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    due_date: date
    stage: InquiryStage
    text: str
