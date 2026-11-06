"""Эндпоинты django-ninja модуля «Снабжение и склад» — вкладки «Материалы» и «Оснастка и
расходники» заказа и экран «Закупки и склад» (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.4, §6; прототип `prTab`, `renderProc`, `prAction`, `newReqDialog`).

Права и роли проверяются здесь (`roleGate` прототипа), сервисы их не проверяют. Каждая
строка отдаёт серверные `abilities`, посчитанные теми же предикатами, что и проверки
действий, — кнопка на фронте и запрет в API не расходятся.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from django.http import Http404, HttpRequest
from django.utils import timezone
from ninja import Query, Router
from ninja.responses import Status

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.core.org import facade as org
from src.production import facade as production
from src.supply import rules, selectors
from src.supply.exceptions import ActorNotEmployee
from src.supply.models import LineCategory, LineKind, LineStatus, PurchaseLine
from src.supply.services import lines as line_services
from src.supply.services import reference as reference_services

from .filters import LineFilters, OrderLinesFilters
from .schemas import (
    DoneOut,
    EmployeeOptionOut,
    EtaIn,
    FilledOut,
    HistoryEntryOut,
    IssueIn,
    LineAbilitiesOut,
    LineCreatedOut,
    LineDetailOut,
    LineIdsIn,
    LineIn,
    LineOut,
    OperationOptionOut,
    OrderedOut,
    OrderLinesIn,
    OrderLinesOut,
    OrderOptionOut,
    ReceiveIn,
    RequisitionIn,
    RequisitionOut,
    ReserveIn,
    SentOut,
    StatusCountsOut,
    SupplierIn,
    SupplierOut,
    SupplyAbilitiesOut,
    SupplyDashboardOut,
    SupplyReferenceOut,
)

router = Router(tags=["supply"])


class AuthenticatedHttpRequest(HttpRequest):
    auth: User


# --- Права --------------------------------------------------------------------------


def _author(user: User) -> UUID:
    employee_id = rules.employee_id_of(user)
    if employee_id is None:
        raise ActorNotEmployee
    return employee_id


def _require_request(user: User) -> UUID:
    if not rules.can_request_lines(user):
        raise PermissionDenied("Потребность и заявки на закупку ведут сотрудники производства.")
    return _author(user)


def _require_order(user: User) -> UUID:
    if not rules.can_order_lines(user):
        raise PermissionDenied("Заказ поставщику и срок поставки ведёт снабжение.")
    return _author(user)


def _require_store(user: User) -> UUID:
    if not rules.can_store_lines(user):
        raise PermissionDenied(
            "Приёмку, резерв и выдачу в цех выполняют начальник склада или начальник производства."
        )
    return _author(user)


def _abilities(user: User) -> SupplyAbilitiesOut:
    return SupplyAbilitiesOut(
        can_request=bool(rules.can_request_lines(user)),
        can_order=bool(rules.can_order_lines(user)),
        can_store=bool(rules.can_store_lines(user)),
    )


def _line_abilities(
    abilities: SupplyAbilitiesOut, line: PurchaseLine, open_orders: set[UUID | None]
) -> LineAbilitiesOut:
    draft = line.status == LineStatus.DRAFT
    return LineAbilitiesOut(
        can_edit=draft and abilities.can_request and line.order_id in open_orders,
        can_send=draft and abilities.can_request,
        can_order=line.status == LineStatus.SENT and abilities.can_order,
        can_change_eta=line.status == LineStatus.ORDERED and abilities.can_order,
        can_receive=line.status == LineStatus.ORDERED and abilities.can_store,
        can_reserve=line.status == LineStatus.SENT and abilities.can_store,
        can_issue=line.status in (LineStatus.RECEIVED, LineStatus.RESERVED) and abilities.can_store,
    )


# --- Преобразования -----------------------------------------------------------------


def _lines_out(user: User, lines: Sequence[PurchaseLine]) -> list[LineOut]:
    today = timezone.localdate()
    orders = production.get_orders_brief({line.order_id for line in lines if line.order_id})
    operations = production.get_operations_brief(
        {line.operation_id for line in lines if line.operation_id}
    )
    open_orders: set[UUID | None] = {
        oid for oid, order in orders.items() if order.stage != production.OrderStage.DONE
    }
    open_orders.add(None)
    abilities = _abilities(user)
    result = []
    for line in lines:
        order = orders.get(line.order_id) if line.order_id else None
        operation = operations.get(line.operation_id) if line.operation_id else None
        result.append(
            LineOut(
                id=line.id,
                order_id=line.order_id,
                order_number=order.number if order else "",
                customer_name=order.customer_name if order else "",
                operation_id=line.operation_id,
                operation_name=f"{operation.seq}. {operation.name}" if operation else "",
                kind=LineKind(line.kind),
                category=LineCategory(line.category),
                name=line.name,
                quantity=line.quantity,
                unit=line.unit,
                price=line.price,
                amount=selectors.amount(line),
                need_date=line.need_date,
                status=LineStatus(line.status),
                requisition_no=line.requisition_no,
                supplier_id=line.supplier_id,
                supplier_name=line.supplier.name if line.supplier else "",
                po_number=line.po_number,
                eta=line.eta,
                received_at=line.received_at,
                received_qty=line.received_qty,
                storage_place=line.storage_place,
                issued_at=line.issued_at,
                issued_to_id=line.issued_to_id,
                issued_to_name=line.issued_to.full_name if line.issued_to else "",
                created_by_name=line.created_by.full_name if line.created_by else "система",
                late_days=selectors.line_late(line, today),
                abilities=_line_abilities(abilities, line, open_orders),
            )
        )
    return result


def _counts_out(counts: selectors.StatusCounts) -> StatusCountsOut:
    return StatusCountsOut(
        draft=counts.draft,
        sent=counts.sent,
        ordered=counts.ordered,
        received=counts.received,
        reserved=counts.reserved,
        issued=counts.issued,
        late=counts.late,
        active_amount=counts.active_amount,
    )


def _line_dto(data: LineIn) -> line_services.LineDTO:
    return line_services.LineDTO(
        kind=data.kind,
        category=data.category,
        name=data.name,
        quantity=data.quantity,
        unit=data.unit,
        price=data.price,
        need_date=data.need_date,
        operation_id=data.operation_id,
    )


def _line_or_404(line_id: UUID) -> PurchaseLine:
    line = selectors.get_line(line_id)
    if line is None:
        raise Http404
    return line


def _order_label(order: production.OrderBrief) -> str:
    return f"{order.number} · {order.product_name} · {order.customer_name}"


# --- Справочники и сводка -----------------------------------------------------------


@router.get("/reference", response=SupplyReferenceOut, operation_id="getSupplyReference")
def get_reference(request: HttpRequest) -> SupplyReferenceOut:
    return SupplyReferenceOut(
        suppliers=[SupplierOut(id=s.id, name=s.name) for s in selectors.list_suppliers()],
        employees=[
            EmployeeOptionOut(id=e.id, full_name=e.full_name)
            for e in sorted(org.list_active_employees(), key=lambda e: e.full_name)
        ],
    )


@router.post("/suppliers", response={201: SupplierOut}, operation_id="createSupplier")
def create_supplier(request: AuthenticatedHttpRequest, payload: SupplierIn) -> Status[SupplierOut]:
    if not rules.can_manage_reference(request.auth):
        raise PermissionDenied("Поставщиков заводят снабжение и склад.")
    supplier_id = reference_services.create_supplier(payload.name, actor_id=request.auth.id)
    return Status(201, SupplierOut(id=supplier_id, name=payload.name.strip()))


@router.get("/dashboard", response=SupplyDashboardOut, operation_id="getSupplyDashboard")
def get_dashboard(request: AuthenticatedHttpRequest) -> SupplyDashboardOut:
    requisitions = selectors.list_requisitions()
    orders = production.get_orders_brief({r.order_id for r in requisitions if r.order_id})
    return SupplyDashboardOut(
        counts=_counts_out(selectors.registry_counts(timezone.localdate())),
        requisitions=[
            RequisitionOut(
                number=r.number,
                order_id=r.order_id,
                order_number=orders[r.order_id].number
                if r.order_id and r.order_id in orders
                else "",
                sent_by_name=r.sent_by_name,
                sent_at=r.sent_at,
                lines=r.lines,
                amount=r.amount,
                ordered=r.ordered,
                in_store=r.in_store,
                issued=r.issued,
            )
            for r in requisitions
        ],
        abilities=_abilities(request.auth),
    )


@router.get("/order-options", response=list[OrderOptionOut], operation_id="listSupplyOrders")
def list_order_options(request: HttpRequest) -> list[OrderOptionOut]:
    """Заказы в работе — «Для чего» в новой заявке на закупку."""

    return [
        OrderOptionOut(id=order.id, label=_order_label(order))
        for order in sorted(production.list_active_orders(), key=lambda o: o.number)
    ]


# --- Строки -------------------------------------------------------------------------


@router.get("/lines", response=list[LineOut], operation_id="listPurchaseLines")
def list_lines(request: AuthenticatedHttpRequest, filters: Query[LineFilters]) -> list[LineOut]:
    lines = selectors.list_lines(
        selectors.LineFilters(
            status=filters.status,
            order_id=filters.order_id,
            warehouse_only=filters.warehouse_only,
            kind=filters.kind,
            category=filters.category,
            late_only=filters.late_only,
            requisition_no=filters.requisition_no,
            search=filters.search,
        ),
        timezone.localdate(),
    )
    return _lines_out(request.auth, lines)


# --- Действия над строками (одной или выбранными) -----------------------------------
# Объявлены раньше `/lines/{line_id}`: Django сопоставляет пути по порядку, и
# `/lines/send` иначе попал бы в маршрут строки.


@router.post("/lines/send", response=SentOut, operation_id="sendPurchaseLines")
def send_lines(request: AuthenticatedHttpRequest, payload: LineIdsIn) -> SentOut:
    author = _require_request(request.auth)
    number = line_services.send_lines(payload.line_ids, actor_id=request.auth.id, author_id=author)
    return SentOut(requisition_no=number)


@router.post("/lines/order", response=OrderedOut, operation_id="orderPurchaseLines")
def order_lines(request: AuthenticatedHttpRequest, payload: OrderLinesIn) -> OrderedOut:
    author = _require_order(request.auth)
    number = line_services.place_order(
        payload.line_ids,
        supplier_id=payload.supplier_id,
        eta=payload.eta,
        po_number=payload.po_number,
        price=payload.price,
        actor_id=request.auth.id,
        author_id=author,
    )
    return OrderedOut(po_number=number)


@router.post("/lines/eta", response=DoneOut, operation_id="changePurchaseLinesEta")
def change_eta(request: AuthenticatedHttpRequest, payload: EtaIn) -> DoneOut:
    author = _require_order(request.auth)
    line_services.change_eta(
        payload.line_ids,
        eta=payload.eta,
        reason=payload.reason,
        actor_id=request.auth.id,
        author_id=author,
    )
    return DoneOut(lines=len(set(payload.line_ids)))


@router.post("/lines/receive", response=DoneOut, operation_id="receivePurchaseLines")
def receive_lines(request: AuthenticatedHttpRequest, payload: ReceiveIn) -> DoneOut:
    author = _require_store(request.auth)
    line_services.receive_lines(
        payload.line_ids,
        received_at=payload.received_at,
        storage_place=payload.storage_place,
        received_qty=payload.received_qty,
        nonconforming=payload.nonconforming,
        remark=payload.remark,
        actor_id=request.auth.id,
        author_id=author,
    )
    return DoneOut(lines=len(set(payload.line_ids)))


@router.post("/lines/reserve", response=DoneOut, operation_id="reservePurchaseLines")
def reserve_lines(request: AuthenticatedHttpRequest, payload: ReserveIn) -> DoneOut:
    author = _require_store(request.auth)
    line_services.reserve_lines(
        payload.line_ids,
        storage_place=payload.storage_place,
        actor_id=request.auth.id,
        author_id=author,
    )
    return DoneOut(lines=len(set(payload.line_ids)))


@router.post("/lines/issue", response=DoneOut, operation_id="issuePurchaseLines")
def issue_lines(request: AuthenticatedHttpRequest, payload: IssueIn) -> DoneOut:
    author = _require_store(request.auth)
    center = production.get_work_center(payload.work_center_id) if payload.work_center_id else None
    line_services.issue_lines(
        payload.line_ids,
        issued_at=payload.issued_at,
        issued_to_id=payload.issued_to_id,
        work_center_name=center.name if center else "",
        actor_id=request.auth.id,
        author_id=author,
    )
    return DoneOut(lines=len(set(payload.line_ids)))


@router.get("/lines/{line_id}", response=LineDetailOut, operation_id="getPurchaseLine")
def get_line(request: AuthenticatedHttpRequest, line_id: UUID) -> LineDetailOut:
    line = _line_or_404(line_id)
    (out,) = _lines_out(request.auth, [line])
    return LineDetailOut(
        **out.model_dump(),
        history=[
            HistoryEntryOut(
                created_at=entry.created_at,
                author_name=entry.author.full_name if entry.author else "система",
                text=entry.text,
            )
            for entry in sorted(line.history.all(), key=lambda e: e.created_at, reverse=True)
        ],
    )


@router.patch("/lines/{line_id}", response=LineOut, operation_id="updatePurchaseLine")
def update_line(request: AuthenticatedHttpRequest, line_id: UUID, payload: LineIn) -> LineOut:
    _require_request(request.auth)
    _line_or_404(line_id)
    line_services.update_line(line_id, _line_dto(payload), actor_id=request.auth.id)
    (out,) = _lines_out(request.auth, [_line_or_404(line_id)])
    return out


@router.delete("/lines/{line_id}", response=DoneOut, operation_id="deletePurchaseLine")
def delete_line(request: AuthenticatedHttpRequest, line_id: UUID) -> DoneOut:
    _require_request(request.auth)
    _line_or_404(line_id)
    line_services.delete_line(line_id, actor_id=request.auth.id)
    return DoneOut(lines=1)


@router.get("/orders/{order_id}/lines", response=OrderLinesOut, operation_id="getOrderSupplyLines")
def get_order_lines(
    request: AuthenticatedHttpRequest, order_id: UUID, filters: Query[OrderLinesFilters]
) -> OrderLinesOut:
    order = production.get_orders_brief([order_id]).get(order_id)
    if order is None:
        raise Http404
    lines = selectors.lines_for_order(order_id, filters.kind)
    today = timezone.localdate()
    return OrderLinesOut(
        order_id=order.id,
        order_number=order.number,
        order_open=order.stage != production.OrderStage.DONE,
        kind=filters.kind,
        lines=_lines_out(request.auth, lines),
        counts=_counts_out(selectors.counts(lines, today)),
        requisitions=sorted({line.requisition_no for line in lines if line.requisition_no}),
        operations=[
            OperationOptionOut(id=op.id, label=f"{op.seq}. {op.name}")
            for op in production.list_order_operations(order_id)
        ],
        abilities=_abilities(request.auth),
    )


@router.post(
    "/orders/{order_id}/lines", response={201: LineCreatedOut}, operation_id="createOrderSupplyLine"
)
def create_order_line(
    request: AuthenticatedHttpRequest, order_id: UUID, payload: LineIn
) -> Status[LineCreatedOut]:
    author = _require_request(request.auth)
    line_id = line_services.create_line(
        order_id, _line_dto(payload), actor_id=request.auth.id, author_id=author
    )
    return Status(201, LineCreatedOut(id=line_id))


@router.post("/orders/{order_id}/fill", response=FilledOut, operation_id="fillOrderSupplyLines")
def fill_order_lines(
    request: AuthenticatedHttpRequest, order_id: UUID, filters: Query[OrderLinesFilters]
) -> FilledOut:
    """«Добавить из калькуляции» (материалы) / «Подобрать по маршруту» (оснастка)."""

    author = _require_request(request.auth)
    added = line_services.fill_order_lines(
        order_id, filters.kind, actor_id=request.auth.id, author_id=author
    )
    return FilledOut(added=added)


@router.post("/requisitions", response={201: SentOut}, operation_id="createRequisition")
def create_requisition(
    request: AuthenticatedHttpRequest, payload: RequisitionIn
) -> Status[SentOut]:
    """Новая заявка на закупку — для заказа или «на склад / ТО», сразу в закупку."""

    author = _require_request(request.auth)
    number = line_services.create_requisition(
        payload.order_id,
        [_line_dto(line) for line in payload.lines],
        actor_id=request.auth.id,
        author_id=author,
    )
    return Status(201, SentOut(requisition_no=number))
