"""Строки потребности: черновики, заявка на закупку, заказ поставщику, приёмка, резерв,
выдача в цех (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4; прототип `prAction`,
`prTab`, `newReqDialog`). Единственное место транзакций для `PurchaseLine` (И3).

Каждое действие пишет историю строки и — у строки заказа — запись журнала заказа
(`production.facade.add_journal_entry(kind="proc")`) в той же транзакции. Права и роли —
в API; групповое действие атомарно: одна неподходящая строка — не выполняется ни одна.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.common.scheduling import add_working_days
from src.core.numbering import facade as numbering
from src.core.org import facade as org
from src.production import facade as production
from src.sales import facade as sales
from src.supply.calculations import late_days, tool_quantity
from src.supply.exceptions import (
    EmployeeNotFound,
    FutureDate,
    InvalidLine,
    InvalidTransition,
    LinesNotFound,
    LinesRequired,
    MixedOrders,
    OperationMismatch,
    OrderClosed,
    OrderNotFound,
    ReasonRequired,
    SingleLineOnly,
    SupplierRequired,
    invalid_transition_as,
)
from src.supply.models import (
    LineCategory,
    LineKind,
    LineStatus,
    PurchaseLine,
    PurchaseLineHistory,
    Supplier,
    ToolTemplate,
)

REQUISITION_NUMERATOR = "supply.requisition"
PURCHASE_ORDER_NUMERATOR = "supply.purchase_order"
DEFAULT_STORAGE = "Склад №1"
# Снабженческая операция «кооперация» (термообработка у подрядчика) — услуга, а не
# поставка материала: материалы к ней не привязываются (`matLines` прототипа).
_SERVICE_OPERATION = re.compile(r"термо|кооперац", re.IGNORECASE)


@dataclass(frozen=True)
class LineDTO:
    kind: LineKind
    category: LineCategory
    name: str
    quantity: Decimal
    need_date: date
    unit: str = "шт"
    price: Decimal = Decimal("0")
    operation_id: UUID | None = None


def fmt(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day is not None else "—"


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _log(
    line: PurchaseLine,
    text: str,
    author_id: UUID | None,
    *,
    at: datetime | None = None,
    journal: bool = True,
) -> None:
    PurchaseLineHistory.objects.create(
        line=line, author_id=author_id, text=text, created_at=at or timezone.now()
    )
    if journal and line.order_id is not None:
        production.add_journal_entry(
            line.order_id,
            production.JournalKind.PROC,
            f"«{line.name}»: {text}",
            operation_id=line.operation_id,
            author_employee_id=author_id,
        )


def _open_order(order_id: UUID) -> production.OrderBrief:
    order = production.get_orders_brief([order_id]).get(order_id)
    if order is None:
        raise OrderNotFound
    if order.stage == production.OrderStage.DONE:
        raise OrderClosed
    return order


def _check_line(order_id: UUID | None, data: LineDTO) -> None:
    if not data.name.strip() or data.quantity <= 0 or data.price < 0:
        raise InvalidLine
    material = data.category == LineCategory.MATERIAL
    if material != (data.kind == LineKind.MATERIAL):
        raise InvalidLine("Материал — вид «материалы», остальное — «оснастка».")
    if data.operation_id is not None:
        if order_id is None:
            raise OperationMismatch
        if data.operation_id not in {op.id for op in production.list_order_operations(order_id)}:
            raise OperationMismatch


def _new_line(order_id: UUID | None, data: LineDTO, author_id: UUID | None) -> PurchaseLine:
    return PurchaseLine.objects.create(
        order_id=order_id,
        operation_id=data.operation_id,
        kind=data.kind,
        category=data.category,
        name=data.name.strip(),
        quantity=data.quantity,
        unit=data.unit.strip() or "шт",
        price=data.price,
        need_date=data.need_date,
        created_by_id=author_id,
    )


def _lock(line_ids: Sequence[UUID]) -> list[PurchaseLine]:
    ids = list(dict.fromkeys(line_ids))
    if not ids:
        raise LinesRequired
    lines = list(
        PurchaseLine.objects.select_for_update(of=("self",))
        .select_related("supplier")
        .filter(id__in=ids)
        .order_by("created_at", "id")
    )
    if len(lines) != len(ids):
        raise LinesNotFound
    return lines


def _check_employee(employee_id: UUID) -> str:
    for brief in org.list_active_employees():
        if brief.id == employee_id:
            return brief.full_name
    raise EmployeeNotFound


# --- Черновики ----------------------------------------------------------------------


def create_line(
    order_id: UUID | None, data: LineDTO, *, actor_id: UUID, author_id: UUID | None
) -> UUID:
    """Черновик позиции («+ позиция» вкладки заказа)."""

    if order_id is not None:
        _open_order(order_id)
    _check_line(order_id, data)
    with transaction.atomic(), actor_context(actor_id):
        line = _new_line(order_id, data, author_id)
        _log(line, "Позиция добавлена", author_id, journal=False)
    return line.id


def _lock_draft(line_id: UUID) -> PurchaseLine:
    line = PurchaseLine.objects.select_for_update().get(id=line_id)
    if line.status != LineStatus.DRAFT:
        raise InvalidTransition("Правится и удаляется только черновик.")
    return line


def update_line(line_id: UUID, data: LineDTO, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        line = _lock_draft(line_id)
        _check_line(line.order_id, data)
        line.kind = data.kind
        line.category = data.category
        line.name = data.name.strip()
        line.quantity = data.quantity
        line.unit = data.unit.strip() or "шт"
        line.price = data.price
        line.need_date = data.need_date
        line.operation_id = data.operation_id
        line.save()


def delete_line(line_id: UUID, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        _lock_draft(line_id).delete()


# --- Потребность заказа -------------------------------------------------------------


def material_drafts(order: production.OrderBrief) -> list[LineDTO]:
    """Материалы калькуляции заявки; срок — окончание снабженческой операции, к которой
    позиция привязана по кругу (`matLines` прототипа)."""

    if order.inquiry_id is None:
        return []
    supply_ops = [
        op
        for op in production.list_order_operations(order.id)
        if op.is_supply and not _SERVICE_OPERATION.search(op.name)
    ]
    result = []
    for i, material in enumerate(sales.get_calc_materials(order.inquiry_id)):
        op = supply_ops[i % len(supply_ops)] if supply_ops else None
        need = (op.planned_finish if op else None) or order.planned_start
        result.append(
            LineDTO(
                kind=LineKind.MATERIAL,
                category=LineCategory.MATERIAL,
                name=material.name,
                quantity=material.quantity,
                price=material.price,
                need_date=need,
                operation_id=op.id if op else None,
            )
        )
    return result


def tool_drafts(order: production.OrderBrief) -> list[LineDTO]:
    """Оснастка и расходники по участкам маршрута (`toolLines`): позиция — один раз на
    заказ, к первой операции участка; срок — за 2 рабочих дня до её начала."""

    templates: dict[UUID, list[ToolTemplate]] = {}
    for template in ToolTemplate.objects.filter(is_active=True):
        templates.setdefault(template.work_center_id, []).append(template)
    seen: set[str] = set()
    result = []
    for op in production.list_order_operations(order.id):
        for template in templates.get(op.work_center_id, []):
            if template.name in seen:
                continue
            seen.add(template.name)
            start = op.planned_start or order.planned_start
            result.append(
                LineDTO(
                    kind=LineKind.TOOL,
                    category=LineCategory(template.category),
                    name=template.name,
                    quantity=tool_quantity(template.category, template.quantity, order.quantity),
                    unit=template.unit,
                    price=template.price,
                    need_date=add_working_days(start, -2),
                    operation_id=op.id,
                )
            )
    return result


def _drafts(order: production.OrderBrief, kind: LineKind) -> list[LineDTO]:
    return material_drafts(order) if kind == LineKind.MATERIAL else tool_drafts(order)


def _journal_added(order_id: UUID, kind: LineKind, count: int, author_id: UUID | None) -> None:
    label = (
        "Потребность в материалах"
        if kind == LineKind.MATERIAL
        else "Оснастка и расходники по маршруту"
    )
    production.add_journal_entry(
        order_id,
        production.JournalKind.PROC,
        f"{label}: добавлено {count} поз.",
        author_employee_id=author_id,
    )


def fill_order_lines(
    order_id: UUID, kind: LineKind, *, actor_id: UUID, author_id: UUID | None
) -> int:
    """«Добавить из калькуляции» / «Подобрать по маршруту»: черновики позиций, которых
    в заказе этого вида ещё нет (по наименованию). Возвращает число добавленных."""

    order = _open_order(order_id)
    with transaction.atomic(), actor_context(actor_id):
        have = set(
            PurchaseLine.objects.filter(order_id=order_id, kind=kind).values_list("name", flat=True)
        )
        drafts = [d for d in _drafts(order, kind) if d.name not in have]
        for data in drafts:
            _log(
                _new_line(order_id, data, author_id), "Позиция добавлена", author_id, journal=False
            )
        if drafts:
            _journal_added(order_id, kind, len(drafts), author_id)
    return len(drafts)


def generate_for_launched_order(order_id: UUID) -> int:
    """Обработчик `production.order_launched`: черновики материалов и оснастки заказа.
    Идемпотентно по заказу — повторная доставка события ничего не добавляет."""

    order = production.get_orders_brief([order_id]).get(order_id)
    if order is None:
        return 0
    created = 0
    with transaction.atomic():
        if PurchaseLine.objects.filter(order_id=order_id).exists():
            return 0
        for kind in (LineKind.MATERIAL, LineKind.TOOL):
            drafts = _drafts(order, kind)
            for data in drafts:
                _log(
                    _new_line(order_id, data, None),
                    "Создано по запуску заказа",
                    None,
                    journal=False,
                )
            if drafts:
                _journal_added(order_id, kind, len(drafts), None)
            created += len(drafts)
    return created


# --- Переходы -----------------------------------------------------------------------


def send_lines(line_ids: Sequence[UUID], *, actor_id: UUID, author_id: UUID | None) -> str:
    """`draft → sent`: строки получают общий номер заявки на закупку."""

    with transaction.atomic(), actor_context(actor_id):
        lines = _lock(line_ids)
        if len({line.order_id for line in lines}) > 1:
            raise MixedOrders
        number = numbering.issue_number(REQUISITION_NUMERATOR)
        now = timezone.now()
        for line in lines:
            with invalid_transition_as(f"«{line.name}»: в закупку передаётся только черновик."):
                line.mark_sent()
            line.requisition_no = number
            line.sent_at = now
            line.sent_by_id = author_id
            line.save(
                update_fields=["status", "requisition_no", "sent_at", "sent_by", "updated_at"]
            )
            _log(line, f"Заявка {number} передана в закупку", author_id)
    return number


def create_requisition(
    order_id: UUID | None,
    lines: Sequence[LineDTO],
    *,
    actor_id: UUID,
    author_id: UUID | None,
) -> str:
    """«Новая заявка на закупку»: позиции заказа или «на склад / ТО» создаются и сразу
    передаются в закупку одной заявкой."""

    if not lines:
        raise LinesRequired
    if order_id is not None:
        _open_order(order_id)
    for data in lines:
        _check_line(order_id, data)
    with transaction.atomic(), actor_context(actor_id):
        created = [_new_line(order_id, data, author_id) for data in lines]
        return send_lines([line.id for line in created], actor_id=actor_id, author_id=author_id)


def _late_suffix(line: PurchaseLine) -> str:
    late = late_days(line.status, line.need_date, line.eta, timezone.localdate())
    return f" — позже потребности на {late} дн." if late > 0 else ""


def place_order(
    line_ids: Sequence[UUID],
    *,
    supplier_id: UUID,
    eta: date,
    po_number: str = "",
    price: Decimal | None = None,
    actor_id: UUID,
    author_id: UUID | None,
) -> str:
    """`sent → ordered` (снабжение): поставщик, срок поставки и номер заказа поставщику
    обязательны; без номера — следующий по нумератору «ЗП-…»."""

    supplier = Supplier.objects.filter(id=supplier_id, is_active=True).first()
    if supplier is None:
        raise SupplierRequired("Поставщик не найден.")
    if price is not None and price < 0:
        raise InvalidLine("Цена не может быть отрицательной.")
    with transaction.atomic(), actor_context(actor_id):
        lines = _lock(line_ids)
        if price is not None and len(lines) > 1:
            raise SingleLineOnly
        number = po_number.strip() or numbering.issue_number(PURCHASE_ORDER_NUMERATOR)
        for line in lines:
            with invalid_transition_as(f"«{line.name}»: заказывается позиция в закупке."):
                line.mark_ordered()
            line.supplier = supplier
            line.po_number = number
            line.eta = eta
            if price is not None:
                line.price = price
            line.save()
            _log(
                line,
                f"Заказано у {supplier.name}, {number}, срок поставки {fmt(eta)}"
                + _late_suffix(line),
                author_id,
            )
    return number


def change_eta(
    line_ids: Sequence[UUID], *, eta: date, reason: str, actor_id: UUID, author_id: UUID | None
) -> None:
    """Перенос срока поставки заказанной позиции — с причиной."""

    reason = reason.strip()
    if not reason:
        raise ReasonRequired
    with transaction.atomic(), actor_context(actor_id):
        for line in _lock(line_ids):
            if line.status != LineStatus.ORDERED:
                raise InvalidTransition(f"«{line.name}»: срок меняется у заказанной позиции.")
            old = line.eta
            line.eta = eta
            line.save(update_fields=["eta", "updated_at"])
            prefix = f"{fmt(old)} → " if old else ""
            _log(
                line,
                f"Срок поставки {prefix}{fmt(eta)}: {reason}" + _late_suffix(line),
                author_id,
            )


def receive_lines(
    line_ids: Sequence[UUID],
    *,
    received_at: date,
    storage_place: str,
    received_qty: Decimal | None = None,
    nonconforming: Decimal = Decimal("0"),
    remark: str = "",
    actor_id: UUID,
    author_id: UUID | None,
) -> None:
    """`ordered → received` (склад): дата, место, фактическое количество (по умолчанию —
    заказанное). Недопоставка и результат входного контроля — в историю и журнал."""

    if received_at > timezone.localdate():
        raise FutureDate
    if (received_qty is not None and received_qty < 0) or nonconforming < 0:
        raise InvalidLine("Количество не может быть отрицательным.")
    place = storage_place.strip() or DEFAULT_STORAGE
    remark = remark.strip()
    with transaction.atomic(), actor_context(actor_id):
        lines = _lock(line_ids)
        if received_qty is not None and len(lines) > 1:
            raise SingleLineOnly
        for line in lines:
            with invalid_transition_as(f"«{line.name}»: принимается заказанная позиция."):
                line.mark_received()
            qty = received_qty if received_qty is not None else line.quantity
            line.received_at = received_at
            line.received_qty = qty
            line.storage_place = place
            line.save()
            text = f"Принято на склад ({place}): {_qty(qty)} {line.unit}"
            if qty < line.quantity:
                text += f" из {_qty(line.quantity)} — недопоставка"
            text += (
                f", входной контроль: не соответствует {_qty(nonconforming)}"
                if nonconforming
                else ", входной контроль пройден"
            )
            _log(line, text + (f". {remark}" if remark else ""), author_id)


def reserve_lines(
    line_ids: Sequence[UUID],
    *,
    storage_place: str = "",
    actor_id: UUID,
    author_id: UUID | None,
) -> None:
    """`sent → reserved` (склад): позиция есть на складе, закупка не требуется."""

    place = storage_place.strip() or DEFAULT_STORAGE
    today = timezone.localdate()
    with transaction.atomic(), actor_context(actor_id):
        for line in _lock(line_ids):
            with invalid_transition_as(f"«{line.name}»: резервируется позиция в закупке."):
                line.mark_reserved()
            line.received_at = today
            line.storage_place = place
            line.save()
            _log(line, "Резерв со склада — закупка не требуется", author_id)


def issue_lines(
    line_ids: Sequence[UUID],
    *,
    issued_at: date,
    issued_to_id: UUID,
    work_center_name: str = "",
    actor_id: UUID,
    author_id: UUID | None,
) -> None:
    """`received / reserved → issued` (склад): кому выдано; участок — в текст записи
    (`prAction('issue')` прототипа)."""

    if issued_at > timezone.localdate():
        raise FutureDate
    recipient = _check_employee(issued_to_id)
    to = (work_center_name.strip() or "ремонтная служба") + f", получил {recipient}"
    with transaction.atomic(), actor_context(actor_id):
        for line in _lock(line_ids):
            with invalid_transition_as(f"«{line.name}»: выдаётся позиция со склада."):
                line.mark_issued()
            line.issued_at = issued_at
            line.issued_to_id = issued_to_id
            line.save()
            _log(line, f"Передано в производство: {to}", author_id)
