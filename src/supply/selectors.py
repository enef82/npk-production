"""Запросы на чтение модуля «Снабжение и склад» (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.4; прототип `prTab`, `renderProc`, `prLate`).

Опоздание строки считается при чтении (`calculations.late_days`), не хранится: оно
меняется само с течением дней.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db.models import Q, QuerySet

from src.supply.calculations import late_days
from src.supply.models import (
    CLOSED_STATUSES,
    LineKind,
    LineStatus,
    PurchaseLine,
    Supplier,
    ToolTemplate,
)

# Порядок реестра (`ord` прототипа): сначала то, что ждёт действия снабжения.
_STATUS_ORDER = {
    LineStatus.DRAFT: 0,
    LineStatus.SENT: 1,
    LineStatus.ORDERED: 2,
    LineStatus.RECEIVED: 3,
    LineStatus.RESERVED: 3,
    LineStatus.ISSUED: 4,
}
# Псевдостатусы фильтра реестра.
FILTER_ACTIVE = "active"  # всё, кроме выданного в цех
FILTER_IN_STORE = "store"  # принято или в резерве — к выдаче в цех


def _lines() -> QuerySet[PurchaseLine]:
    return PurchaseLine.objects.select_related("supplier", "issued_to", "created_by", "sent_by")


def line_late(line: PurchaseLine, today: date) -> int:
    return late_days(line.status, line.need_date, line.eta, today)


def amount(line: PurchaseLine) -> Decimal:
    result: Decimal = line.quantity * line.price
    return result


@dataclass(frozen=True)
class LineFilters:
    status: str = FILTER_ACTIVE
    order_id: UUID | None = None
    warehouse_only: bool = False
    kind: LineKind | None = None
    category: str | None = None
    late_only: bool = False
    requisition_no: str = ""
    search: str = ""
    include_drafts: bool = False


def list_lines(filters: LineFilters, today: date) -> list[PurchaseLine]:
    """Реестр «Закупки и склад»: опаздывающие сверху, затем по статусу и сроку."""

    lines = _lines()
    if not filters.include_drafts:
        lines = lines.exclude(status=LineStatus.DRAFT)
    if filters.status == FILTER_ACTIVE:
        lines = lines.exclude(status=LineStatus.ISSUED)
    elif filters.status == FILTER_IN_STORE:
        lines = lines.filter(status__in=(LineStatus.RECEIVED, LineStatus.RESERVED))
    elif filters.status:
        lines = lines.filter(status=filters.status)
    if filters.order_id is not None:
        lines = lines.filter(order_id=filters.order_id)
    if filters.warehouse_only:
        lines = lines.filter(order_id__isnull=True)
    if filters.kind is not None:
        lines = lines.filter(kind=filters.kind)
    if filters.category:
        lines = lines.filter(category=filters.category)
    if filters.requisition_no:
        lines = lines.filter(requisition_no=filters.requisition_no)
    if filters.search.strip():
        text = filters.search.strip()
        lines = lines.filter(
            Q(name__icontains=text)
            | Q(requisition_no__icontains=text)
            | Q(po_number__icontains=text)
            | Q(supplier__name__icontains=text)
        )
    result = list(lines)
    if filters.late_only:
        result = [line for line in result if line_late(line, today) > 0]
    result.sort(
        key=lambda line: (-line_late(line, today), _STATUS_ORDER[line.status], line.need_date)
    )
    return result


def lines_for_order(order_id: UUID, kind: LineKind | None = None) -> list[PurchaseLine]:
    lines = _lines().filter(order_id=order_id)
    if kind is not None:
        lines = lines.filter(kind=kind)
    return list(lines.order_by("need_date", "created_at"))


def lines_by_operation(operation_ids: Iterable[UUID]) -> dict[UUID, list[PurchaseLine]]:
    result: dict[UUID, list[PurchaseLine]] = defaultdict(list)
    for line in _lines().filter(operation_id__in=list(operation_ids)).order_by("need_date"):
        assert line.operation_id is not None
        result[line.operation_id].append(line)
    return result


def get_line(line_id: UUID) -> PurchaseLine | None:
    return _lines().prefetch_related("history__author").filter(id=line_id).first()


def list_suppliers() -> list[Supplier]:
    return list(Supplier.objects.filter(is_active=True))


def list_tool_templates() -> list[ToolTemplate]:
    return list(ToolTemplate.objects.filter(is_active=True))


# --- Сводки -------------------------------------------------------------------------


@dataclass
class StatusCounts:
    draft: int = 0
    sent: int = 0
    ordered: int = 0
    received: int = 0
    reserved: int = 0
    issued: int = 0
    late: int = 0
    # Сумма позиций, ещё не выданных в цех (без черновиков).
    active_amount: Decimal = Decimal("0")

    def add(self, line: PurchaseLine, today: date) -> None:
        setattr(self, line.status, getattr(self, line.status) + 1)
        if line_late(line, today) > 0:
            self.late += 1
        if line.status not in (LineStatus.DRAFT, LineStatus.ISSUED):
            self.active_amount += amount(line)


def counts(lines: Iterable[PurchaseLine], today: date) -> StatusCounts:
    result = StatusCounts()
    for line in lines:
        result.add(line, today)
    return result


def order_status(order_id: UUID, today: date) -> StatusCounts:
    return counts(PurchaseLine.objects.filter(order_id=order_id), today)


def registry_counts(today: date) -> StatusCounts:
    return counts(PurchaseLine.objects.exclude(status=LineStatus.DRAFT), today)


@dataclass
class Requisition:
    number: str
    order_id: UUID | None
    sent_by_name: str
    sent_at: datetime | None
    lines: int = 0
    amount: Decimal = Decimal("0")
    ordered: int = 0
    in_store: int = 0
    issued: int = 0


def list_requisitions() -> list[Requisition]:
    """Реестр заявок на закупку — группировка строк по номеру заявки, новые сверху."""

    groups: dict[str, Requisition] = {}
    lines = (
        PurchaseLine.objects.exclude(status=LineStatus.DRAFT)
        .select_related("sent_by")
        .order_by("sent_at", "created_at")
    )
    for line in lines:
        req = groups.get(line.requisition_no)
        if req is None:
            req = groups[line.requisition_no] = Requisition(
                number=line.requisition_no,
                order_id=line.order_id,
                sent_by_name=line.sent_by.full_name if line.sent_by else "",
                sent_at=line.sent_at,
            )
        req.lines += 1
        req.amount += amount(line)
        if line.status == LineStatus.ORDERED:
            req.ordered += 1
        elif line.status == LineStatus.ISSUED:
            req.issued += 1
        elif line.status in CLOSED_STATUSES:
            req.in_store += 1
    return sorted(
        groups.values(), key=lambda r: r.sent_at.timestamp() if r.sent_at else 0, reverse=True
    )
