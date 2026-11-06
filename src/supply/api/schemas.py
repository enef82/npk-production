"""Pydantic-схемы входа и выхода API модуля «Снабжение и склад»."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Field, Schema

from src.supply.models import LineCategory, LineKind, LineStatus

# --- Справочники ---


class SupplierOut(Schema):
    id: UUID
    name: str


class SupplierIn(Schema):
    name: str


class SupplyEmployeeOptionOut(Schema):
    id: UUID
    full_name: str


class SupplyReferenceOut(Schema):
    suppliers: list[SupplierOut]
    # Кому выдать в производство — работающие сотрудники.
    employees: list[SupplyEmployeeOptionOut]


# --- Строки ---


class LineAbilitiesOut(Schema):
    """Действия над строкой, доступные текущему пользователю в её статусе."""

    can_edit: bool
    can_send: bool
    can_order: bool
    can_change_eta: bool
    can_receive: bool
    can_reserve: bool
    can_issue: bool


class LineOut(Schema):
    id: UUID
    order_id: UUID | None
    order_number: str
    customer_name: str
    operation_id: UUID | None
    operation_name: str
    kind: LineKind
    category: LineCategory
    name: str
    quantity: Decimal
    unit: str
    price: Decimal
    amount: Decimal
    need_date: date
    status: LineStatus
    requisition_no: str
    supplier_id: UUID | None
    supplier_name: str
    po_number: str
    eta: date | None
    received_at: date | None
    received_qty: Decimal | None
    storage_place: str
    issued_at: date | None
    issued_to_id: UUID | None
    issued_to_name: str
    created_by_name: str
    late_days: int
    abilities: LineAbilitiesOut


class HistoryEntryOut(Schema):
    created_at: datetime
    author_name: str
    text: str


class LineDetailOut(LineOut):
    history: list[HistoryEntryOut]


class StatusCountsOut(Schema):
    draft: int
    sent: int
    ordered: int
    received: int
    reserved: int
    issued: int
    late: int
    active_amount: Decimal


class SupplyAbilitiesOut(Schema):
    can_request: bool
    can_order: bool
    can_store: bool


class SupplyOperationOptionOut(Schema):
    id: UUID
    label: str


class OrderLinesOut(Schema):
    """Вкладка «Материалы» / «Оснастка и расходники» заказа (`prTab` прототипа)."""

    order_id: UUID
    order_number: str
    order_open: bool
    kind: LineKind
    lines: list[LineOut]
    counts: StatusCountsOut
    requisitions: list[str]
    operations: list[SupplyOperationOptionOut]
    abilities: SupplyAbilitiesOut


class RequisitionOut(Schema):
    number: str
    order_id: UUID | None
    order_number: str
    sent_by_name: str
    sent_at: datetime | None
    lines: int
    amount: Decimal
    ordered: int
    in_store: int
    issued: int


class SupplyDashboardOut(Schema):
    counts: StatusCountsOut
    requisitions: list[RequisitionOut]
    abilities: SupplyAbilitiesOut


class SupplyOrderOptionOut(Schema):
    id: UUID
    label: str


class LineIn(Schema):
    kind: LineKind
    category: LineCategory
    name: str
    quantity: Decimal = Field(..., gt=0)
    unit: str = "шт"
    price: Decimal = Field(Decimal("0"), ge=0)
    need_date: date
    operation_id: UUID | None = None


class RequisitionIn(Schema):
    order_id: UUID | None = None
    lines: list[LineIn]


class LineIdsIn(Schema):
    line_ids: list[UUID]


class SentOut(Schema):
    requisition_no: str


class OrderLinesIn(LineIdsIn):
    supplier_id: UUID
    eta: date
    po_number: str = ""
    price: Decimal | None = None


class OrderedOut(Schema):
    po_number: str


class EtaIn(LineIdsIn):
    eta: date
    reason: str


class ReceiveIn(LineIdsIn):
    received_at: date
    storage_place: str = ""
    received_qty: Decimal | None = None
    nonconforming: Decimal = Decimal("0")
    remark: str = ""


class ReserveIn(LineIdsIn):
    storage_place: str = ""


class IssueIn(LineIdsIn):
    issued_at: date
    issued_to_id: UUID
    work_center_id: UUID | None = None


class DoneOut(Schema):
    """Сколько строк затронуло действие. Тело вместо 204: клиент API разбирает JSON
    по заголовку ответа, а пустой 204 с `application/json` он разобрать не может."""

    lines: int


class FilledOut(Schema):
    added: int


class LineCreatedOut(Schema):
    id: UUID
