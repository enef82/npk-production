"""Запросы на чтение модуля «Производство»: справочники, доска, карточка заказа, план с
критическим путём, Гант, «Мои визы», журнал, документы
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, §6).

Списки собираются фиксированным числом запросов (`prefetch_related`), арифметика графика
— `core.common.scheduling` по хранимым `planned_start`. Критический путь, резерв и
нарушения связей не хранятся (§2.1).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db.models import F, Prefetch, Q, QuerySet, Sum
from django.utils import timezone

from src.core.common.scheduling import (
    Health,
    HealthColor,
    ScheduleAnalysis,
    analyze,
    assess_health,
)
from src.core.documents import facade as documents
from src.core.org import selectors as org_selectors
from src.core.org.models import Employee
from src.production.models import (
    DocumentRelease,
    JournalKind,
    Operation,
    OperationDependency,
    OperationEarning,
    OperationStatus,
    OrderJournalEntry,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
    ProductionSettings,
    ProductTemplate,
    TemplateOperation,
    WorkCenter,
    WorkPhase,
)
from src.production.planning import duration_of, finish_of, network
from src.quality import facade as quality

ORDER_ENTITY = "production.order"
OPERATION_ENTITY = "production.operation"

# Виды документов заказа (§3.1) — засеяны миграцией `0005_seed_document_types`.
DOCUMENT_TYPE_CODES: dict[str, str] = {
    "production.kd": "КД",
    "production.drawing": "Чертёж",
    "production.tz": "ТЗ / опросный лист",
    "production.specification": "Спецификация",
    "production.process": "Техпроцесс",
    "production.cnc": "УП ЧПУ",
    "production.other": "Прочее",
}
# «Подготовка не закрывается без КД» — годится КД или чертёж.
KD_CODES = ("production.kd", "production.drawing")

WORK_STAGES = (OrderStage.PREP, OrderStage.PROD, OrderStage.QC)
_PCT_QUANT = Decimal("0.1")


def document_type_name(code: str) -> str:
    return DOCUMENT_TYPE_CODES.get(code, code)


def _name(employee: Employee | None) -> str:
    return employee.full_name if employee is not None else ""


# --- Справочники -------------------------------------------------------------------


def list_employees() -> list[org_selectors.EmployeeBrief]:
    """Работающие сотрудники для выбора ответственных за этапы и операции."""

    return org_selectors.list_active_employees()


def list_work_centers(*, active_only: bool = False) -> list[WorkCenter]:
    qs = WorkCenter.objects.select_related("responsible")
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs)


def get_work_center(work_center_id: UUID) -> WorkCenter | None:
    return WorkCenter.objects.select_related("responsible").filter(id=work_center_id).first()


def _templates() -> QuerySet[ProductTemplate]:
    return ProductTemplate.objects.prefetch_related(
        "materials",
        Prefetch(
            "operations",
            queryset=TemplateOperation.objects.select_related("work_center").prefetch_related(
                "predecessor_links"
            ),
        ),
    )


def list_templates(*, active_only: bool = False) -> list[ProductTemplate]:
    qs = _templates()
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs)


def get_template(code_or_id: str | UUID) -> ProductTemplate | None:
    if isinstance(code_or_id, UUID):
        return _templates().filter(id=code_or_id).first()
    try:
        return _templates().filter(id=UUID(code_or_id)).first()
    except ValueError:
        return _templates().filter(code=code_or_id).first()


def get_settings() -> ProductionSettings | None:
    return (
        ProductionSettings.objects.select_related(
            "launch_responsible", "prep_responsible", "prod_responsible", "qc_responsible"
        )
        .filter()
        .first()
    )


# --- Общие расчёты по заказу -------------------------------------------------------


@dataclass(frozen=True)
class HealthView:
    color: str
    status: str
    days: int
    text: str


def health_text(health: Health, *, is_order: bool) -> str:
    if health.status == "done":
        return "Отгружен"
    if health.status == "no_plan":
        return "Нет плана"
    if health.status == "late":
        prefix = "Срыв срока на" if is_order else "Не укладываемся на"
        return f"{prefix} {health.days} дн."
    if health.status == "lagging":
        return "Есть отставание"
    if health.status == "tight":
        return f"Запас {health.days} дн."
    return "В графике" if is_order else "Укладываемся"


def _health(order: ProductionOrder, operations: Sequence[Operation]) -> HealthView:
    finishes = [finish_of(op) for op in operations]
    has_plan = bool(operations) and all(f is not None for f in finishes)
    finish = max((f for f in finishes if f is not None), default=None)
    today = timezone.localdate()
    lagging = any(
        op.status != OperationStatus.DONE and f is not None and f < today
        for op, f in zip(operations, finishes, strict=True)
    )
    health = assess_health(
        finish=finish,
        due=order.due_date,
        has_plan=has_plan,
        is_done=order.stage == OrderStage.DONE,
        is_lagging=lagging,
    )
    return HealthView(
        color=HealthColor(health.color).value,
        status=health.status,
        days=health.days,
        text=health_text(health, is_order=True),
    )


def progress_of(operations: Iterable[Operation]) -> Decimal:
    """`progress()` прототипа: средний процент, взвешенный нормо-часами; снабжение не
    весит ничего."""

    total = Decimal("0")
    weighted = Decimal("0")
    for op in operations:
        if op.work_center.is_supply:
            continue
        total += op.hours
        pct = 100 if op.status == OperationStatus.DONE else op.progress
        weighted += op.hours * pct
    if not total:
        return Decimal("0.0")
    return (weighted / total).quantize(_PCT_QUANT, ROUND_HALF_UP)


def derived_stage(operations: Sequence[Operation]) -> OrderStage:
    """`deriveStage` прототипа — подсказка на доске, куда заказ можно переводить."""

    open_ops = [op for op in operations if op.status != OperationStatus.DONE]
    if any(op.work_center.phase == WorkPhase.PREP for op in open_ops):
        return OrderStage.PREP
    if any(op.work_center.phase != WorkPhase.QC for op in open_ops):
        return OrderStage.PROD
    if open_ops:
        return OrderStage.QC
    return OrderStage.DONE


def _planned_finish(operations: Iterable[Operation]) -> date | None:
    return max((f for f in (finish_of(op) for op in operations) if f is not None), default=None)


def order_planned_finish(order_id: UUID) -> date | None:
    return _planned_finish(
        Operation.objects.filter(order_id=order_id).select_related("work_center")
    )


def order_has_kd(order_id: UUID) -> bool:
    return documents.DocumentLink.objects.filter(
        entity_type=ORDER_ENTITY,
        entity_id=order_id,
        document__doc_type__code__in=KD_CODES,
    ).exists()


# --- Доска -------------------------------------------------------------------------


@dataclass(frozen=True)
class StageApprovalView:
    stage: str
    stage_label: str
    responsible_id: UUID | None
    responsible_name: str
    approved_by_id: UUID | None
    approved_by_name: str
    approved_at: datetime | None
    comment: str


@dataclass(frozen=True)
class OrderCard:
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
    stage: str
    derived_stage: str
    health: HealthView
    progress: Decimal
    stage_responsible_id: UUID | None
    stage_responsible_name: str
    stage_approved: bool
    contract_total: Decimal
    operations_total: int
    operations_done: int


def _orders_with_plan() -> QuerySet[ProductionOrder]:
    return ProductionOrder.objects.select_related("manager").prefetch_related(
        Prefetch(
            "operations",
            queryset=Operation.objects.select_related("work_center").order_by("seq"),
        ),
        Prefetch(
            "stage_approvals",
            queryset=OrderStageApproval.objects.select_related("responsible", "approved_by"),
        ),
    )


def _approval_view(approval: OrderStageApproval) -> StageApprovalView:
    return StageApprovalView(
        stage=approval.stage,
        stage_label=str(OrderStage(approval.stage).label),
        responsible_id=approval.responsible_id,
        responsible_name=_name(approval.responsible),
        approved_by_id=approval.approved_by_id,
        approved_by_name=_name(approval.approved_by),
        approved_at=approval.approved_at,
        comment=approval.comment,
    )


def _card(order: ProductionOrder) -> OrderCard:
    operations = list(order.operations.all())
    current = next((a for a in order.stage_approvals.all() if a.stage == order.stage), None)
    return OrderCard(
        id=order.id,
        number=order.number,
        inquiry_id=order.inquiry_id,
        inquiry_number=order.inquiry_number,
        customer_id=order.customer_id,
        customer_name=order.customer_name,
        object_name=order.object_name,
        product_name=order.product_name,
        quantity=order.quantity,
        manager_id=order.manager_id,
        manager_name=_name(order.manager),
        planned_start=order.planned_start,
        planned_finish=_planned_finish(operations),
        due_date=order.due_date,
        stage=order.stage,
        derived_stage=derived_stage(operations),
        health=_health(order, operations),
        progress=progress_of(operations),
        stage_responsible_id=current.responsible_id if current else None,
        stage_responsible_name=_name(current.responsible) if current else "",
        stage_approved=bool(current and current.approved_at is not None),
        contract_total=order.contract_total,
        operations_total=len(operations),
        operations_done=sum(1 for op in operations if op.status == OperationStatus.DONE),
    )


def list_board(
    *, stage: OrderStage | None = None, search: str = "", active_only: bool = False
) -> list[OrderCard]:
    """Карточки доски — четыре запроса независимо от числа заказов."""

    qs = _orders_with_plan().order_by("due_date", "number")
    if stage is not None:
        qs = qs.filter(stage=stage)
    if active_only:
        qs = qs.exclude(stage=OrderStage.DONE)
    if search.strip():
        term = search.strip()
        qs = qs.filter(
            Q(number__icontains=term)
            | Q(inquiry_number__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(object_name__icontains=term)
            | Q(product_name__icontains=term)
        )
    return [_card(order) for order in qs]


@dataclass(frozen=True)
class OrderDetail(OrderCard):
    template_id: UUID | None
    labor_cost_planned: Decimal
    shipped_at: datetime | None
    created_at: datetime
    approvals: list[StageApprovalView]
    hours_total: Decimal
    earned_total: Decimal
    has_kd: bool


def get_order_detail(order_id: UUID) -> OrderDetail | None:
    order = _orders_with_plan().filter(id=order_id).first()
    if order is None:
        return None
    card = _card(order)
    operations = list(order.operations.all())
    earned = OperationEarning.objects.filter(operation__order=order).aggregate(s=Sum("hours"))["s"]
    order_index = {stage: i for i, stage in enumerate(OrderStage.values)}
    approvals = sorted(order.stage_approvals.all(), key=lambda a: order_index[a.stage])
    return OrderDetail(
        **card.__dict__,
        template_id=order.template_id,
        labor_cost_planned=order.labor_cost_planned,
        shipped_at=order.shipped_at,
        created_at=order.created_at,
        approvals=[_approval_view(a) for a in approvals],
        hours_total=sum(
            (op.hours for op in operations if not op.work_center.is_supply), Decimal("0")
        ),
        earned_total=earned if earned is not None else Decimal("0"),
        has_kd=order_has_kd(order.id),
    )


def get_order(order_id: UUID) -> ProductionOrder | None:
    return ProductionOrder.objects.select_related("manager").filter(id=order_id).first()


def get_stage_approval(order_id: UUID, stage: str) -> OrderStageApproval | None:
    return OrderStageApproval.objects.filter(order_id=order_id, stage=stage).first()


# --- План заказа -------------------------------------------------------------------


@dataclass(frozen=True)
class OperationRow:
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
    status: str
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


def _analysis(
    operations: Sequence[Operation], dependencies: Sequence[OperationDependency]
) -> ScheduleAnalysis | None:
    if not operations or any(op.planned_start is None for op in operations):
        return None
    nodes, edges = network(operations, dependencies)
    starts = {op.id: op.planned_start for op in operations if op.planned_start is not None}
    return analyze(nodes, edges, starts)


def _inspection_map(operations: Iterable[Operation]) -> dict[UUID, bool]:
    # Раз на участок, а не на операцию: фасад `quality` может ходить в БД.
    return {wc: quality.requires_inspection(wc) for wc in {op.work_center_id for op in operations}}


def _rows(
    operations: Sequence[Operation],
    dependencies: Sequence[OperationDependency],
    earned: dict[UUID, Decimal],
    inspections: dict[UUID, bool],
) -> tuple[list[OperationRow], ScheduleAnalysis | None]:
    analysis = _analysis(operations, dependencies)
    preds: dict[UUID, list[UUID]] = defaultdict(list)
    for dep in dependencies:
        preds[dep.successor_id].append(dep.predecessor_id)
    rows = []
    for op in operations:
        node = analysis.nodes.get(op.id) if analysis else None
        center = op.work_center
        rows.append(
            OperationRow(
                id=op.id,
                order_id=op.order_id,
                seq=op.seq,
                name=op.name,
                work_center_id=center.id,
                work_center_short_name=center.short_name,
                work_center_name=center.name,
                phase=center.phase,
                is_supply=center.is_supply,
                capacity=center.capacity,
                hours=op.hours,
                people=op.people,
                duration=duration_of(op),
                responsible_id=op.responsible_id,
                responsible_name=_name(op.responsible),
                not_before=op.not_before,
                planned_start=op.planned_start,
                planned_finish=finish_of(op),
                status=op.status,
                progress=op.progress,
                earned_hours=earned.get(op.id, Decimal("0")),
                started_at=op.started_at,
                approved_at=op.approved_at,
                approved_by_name=_name(op.approved_by),
                approved_for_name=_name(op.approved_for),
                predecessor_ids=preds.get(op.id, []),
                slack=node.slack if node else None,
                is_critical=bool(node and node.is_critical),
                violates_dependency=bool(node and node.violates_dependency),
                requires_inspection=inspections.get(center.id, False),
            )
        )
    return rows, analysis


def _operations_qs() -> QuerySet[Operation]:
    return Operation.objects.select_related(
        "work_center", "responsible", "approved_by", "approved_for"
    ).order_by("seq")


def _earned_by_operation(operation_filter: Q) -> dict[UUID, Decimal]:
    return {
        row["operation_id"]: row["total"]
        for row in OperationEarning.objects.filter(operation_filter)
        .values("operation_id")
        .annotate(total=Sum("hours"))
    }


@dataclass(frozen=True)
class OrderSchedule:
    order_id: UUID
    planned_start: date
    planned_finish: date | None
    due_date: date
    length: int
    critical_path: list[UUID]
    has_violations: bool
    operations: list[OperationRow]


def get_order_schedule(order_id: UUID) -> OrderSchedule | None:
    order = ProductionOrder.objects.filter(id=order_id).first()
    if order is None:
        return None
    operations = list(_operations_qs().filter(order=order))
    dependencies = list(OperationDependency.objects.filter(successor__order=order))
    rows, analysis = _rows(
        operations,
        dependencies,
        _earned_by_operation(Q(operation__order=order)),
        _inspection_map(operations),
    )
    return OrderSchedule(
        order_id=order.id,
        planned_start=order.planned_start,
        planned_finish=analysis.finish if analysis else None,
        due_date=order.due_date,
        length=analysis.length if analysis else 0,
        critical_path=analysis.critical_path if analysis else [],
        has_violations=any(row.violates_dependency for row in rows),
        operations=rows,
    )


# --- Гант всех заказов -------------------------------------------------------------


@dataclass(frozen=True)
class GanttOrder:
    id: UUID
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    stage: str
    due_date: date
    planned_start: date
    planned_finish: date | None
    health: HealthView
    operations: list[OperationRow]


def list_gantt() -> list[GanttOrder]:
    """Все не отгруженные заказы с операциями и критическим путём — пять запросов."""

    orders = list(
        ProductionOrder.objects.exclude(stage=OrderStage.DONE)
        .prefetch_related(Prefetch("operations", queryset=_operations_qs()))
        .order_by("planned_start", "number")
    )
    order_ids = [order.id for order in orders]
    deps_by_order: dict[UUID, list[OperationDependency]] = defaultdict(list)
    for dep in OperationDependency.objects.filter(successor__order_id__in=order_ids).annotate(
        order_ref=F("successor__order_id")
    ):
        deps_by_order[dep.order_ref].append(dep)
    earned = _earned_by_operation(Q(operation__order_id__in=order_ids))
    all_ops = [op for order in orders for op in order.operations.all()]
    inspections = _inspection_map(all_ops)
    result = []
    for order in orders:
        operations = list(order.operations.all())
        rows, analysis = _rows(operations, deps_by_order[order.id], earned, inspections)
        result.append(
            GanttOrder(
                id=order.id,
                number=order.number,
                customer_name=order.customer_name,
                product_name=order.product_name,
                quantity=order.quantity,
                stage=order.stage,
                due_date=order.due_date,
                planned_start=order.planned_start,
                planned_finish=analysis.finish if analysis else None,
                health=_health(order, operations),
                operations=rows,
            )
        )
    return result


# --- Карточка операции -------------------------------------------------------------


@dataclass(frozen=True)
class OperationLink:
    id: UUID
    seq: int
    name: str
    status: str
    planned_start: date | None
    planned_finish: date | None


@dataclass(frozen=True)
class DocumentRow:
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


@dataclass(frozen=True)
class JournalRow:
    id: UUID
    created_at: datetime
    kind: str
    kind_label: str
    stage: str
    operation_id: UUID | None
    operation_label: str
    author_id: UUID | None
    author_name: str
    text: str


@dataclass(frozen=True)
class OperationCard:
    operation: OperationRow
    order: OrderCard
    predecessors: list[OperationLink]
    successors: list[OperationLink]
    documents: list[DocumentRow]
    journal: list[JournalRow]
    has_inspection: bool


def get_operation(operation_id: UUID) -> Operation | None:
    return Operation.objects.select_related("work_center", "order").filter(id=operation_id).first()


def _link(op: Operation) -> OperationLink:
    return OperationLink(
        id=op.id,
        seq=op.seq,
        name=op.name,
        status=op.status,
        planned_start=op.planned_start,
        planned_finish=finish_of(op),
    )


def get_operation_card(operation_id: UUID) -> OperationCard | None:
    operation = Operation.objects.filter(id=operation_id).only("id", "order_id").first()
    if operation is None:
        return None
    order = _orders_with_plan().get(id=operation.order_id)
    schedule = get_order_schedule(order.id)
    assert schedule is not None
    by_id = {op.id: op for op in order.operations.all()}
    row = next(r for r in schedule.operations if r.id == operation_id)
    successors = [r.id for r in schedule.operations if operation_id in r.predecessor_ids]
    return OperationCard(
        operation=row,
        order=_card(order),
        predecessors=[_link(by_id[pid]) for pid in row.predecessor_ids],
        successors=[_link(by_id[sid]) for sid in successors],
        documents=[d for d in list_order_documents(order.id) if d.operation_id == operation_id],
        journal=list_journal(order.id, operation_id=operation_id),
        has_inspection=quality.has_inspection(operation_id),
    )


# --- Документы ---------------------------------------------------------------------


def list_order_documents(order_id: UUID) -> list[DocumentRow]:
    links = list(
        documents.DocumentLink.objects.filter(entity_type=ORDER_ENTITY, entity_id=order_id)
        .select_related("document__doc_type")
        .order_by("-document__created_at")
    )
    operation_ids = list(Operation.objects.filter(order_id=order_id).values_list("id", flat=True))
    op_links = {
        link.document_id: link.entity_id
        for link in documents.DocumentLink.objects.filter(
            entity_type=OPERATION_ENTITY,
            entity_id__in=operation_ids,
            document_id__in=[link.document_id for link in links],
        )
    }
    releases = {
        release.document_id: release
        for release in DocumentRelease.objects.filter(order_id=order_id).select_related(
            "approved_by"
        )
    }
    rows = []
    for link in links:
        doc = link.document
        release = releases.get(doc.id)
        rows.append(
            DocumentRow(
                document_id=doc.id,
                name=doc.original_name,
                doc_type_code=doc.doc_type.code,
                doc_type_name=doc.doc_type.name,
                version=doc.version,
                size_bytes=doc.size_bytes,
                uploaded_at=doc.created_at,
                operation_id=op_links.get(doc.id),
                approved_by_name=_name(release.approved_by) if release else "",
                approved_at=release.approved_at if release else None,
            )
        )
    return rows


def is_order_document(document_id: UUID) -> bool:
    return documents.DocumentLink.objects.filter(
        document_id=document_id, entity_type=ORDER_ENTITY
    ).exists()


# --- Журнал ------------------------------------------------------------------------


def list_journal(
    order_id: UUID,
    *,
    operation_id: UUID | None = None,
    kind: JournalKind | None = None,
    author_id: UUID | None = None,
) -> list[JournalRow]:
    qs = OrderJournalEntry.objects.filter(order_id=order_id).select_related("author", "operation")
    if operation_id is not None:
        qs = qs.filter(operation_id=operation_id)
    if kind is not None:
        qs = qs.filter(kind=kind)
    if author_id is not None:
        qs = qs.filter(author_id=author_id)
    return [
        JournalRow(
            id=entry.id,
            created_at=entry.created_at,
            kind=entry.kind,
            kind_label=str(JournalKind(entry.kind).label),
            stage=entry.stage,
            operation_id=entry.operation_id,
            operation_label=(
                f"{entry.operation.seq}. {entry.operation.name}" if entry.operation else ""
            ),
            author_id=entry.author_id,
            author_name=_name(entry.author) if entry.author else "система",
            text=entry.text,
        )
        for entry in qs.order_by("-created_at", "-id")
    ]


# --- «Мои визы» --------------------------------------------------------------------


@dataclass(frozen=True)
class VisaItem:
    kind: str  # "stage" | "operation"
    order_id: UUID
    order_number: str
    product_name: str
    customer_name: str
    quantity: Decimal
    due_date: date
    health: HealthView
    stage: str
    operation_id: UUID | None
    operation_name: str
    operation_status: str
    text: str


def list_my_visas(employee_id: UUID) -> list[VisaItem]:
    """`myVisaList` прототипа: текущие этапы заказов, где я ответственный и визы нет, и
    операции, где я ответственный, а операция на визе (или закупка в работе) и все
    предшественники закрыты."""

    stage_approvals = list(
        OrderStageApproval.objects.filter(
            responsible_id=employee_id, approved_at__isnull=True, stage=F("order__stage")
        )
        .exclude(stage=OrderStage.DONE)
        .values_list("order_id", "stage")
    )
    open_statuses = [OperationStatus.WAIT, OperationStatus.WORK, OperationStatus.CHECK]
    operations = list(
        Operation.objects.filter(
            responsible_id=employee_id,
            order__stage__in=WORK_STAGES,
        )
        .filter(
            Q(status=OperationStatus.CHECK)
            | Q(status=OperationStatus.WORK, work_center__is_supply=True)
        )
        .exclude(predecessor_links__predecessor__status__in=open_statuses)
        .order_by("seq")
    )
    order_ids = {order_id for order_id, _ in stage_approvals} | {op.order_id for op in operations}
    orders = {order.id: order for order in _orders_with_plan().filter(id__in=order_ids)}
    health = {oid: _health(order, list(order.operations.all())) for oid, order in orders.items()}

    def item(order: ProductionOrder, **kwargs: object) -> VisaItem:
        return VisaItem(
            order_id=order.id,
            order_number=order.number,
            product_name=order.product_name,
            customer_name=order.customer_name,
            quantity=order.quantity,
            due_date=order.due_date,
            health=health[order.id],
            stage=order.stage,
            **kwargs,  # type: ignore[arg-type]
        )

    result = [
        item(
            orders[order_id],
            kind="stage",
            operation_id=None,
            operation_name="",
            operation_status="",
            text=f"Этап «{OrderStage(stage).label}»",
        )
        for order_id, stage in stage_approvals
    ]
    for op in operations:
        suffix = (
            " — выполнена, на визе" if op.status == OperationStatus.CHECK else " — закупка в работе"
        )
        result.append(
            item(
                orders[op.order_id],
                kind="operation",
                operation_id=op.id,
                operation_name=op.name,
                operation_status=op.status,
                text=f"Операция «{op.name}»{suffix}",
            )
        )
    result.sort(key=lambda v: (v.due_date, v.order_number))
    return result


# --- Для фасада --------------------------------------------------------------------


def list_orders_with_operations(
    *, ids: Iterable[UUID] | None = None, active_only: bool = False
) -> list[ProductionOrder]:
    qs = ProductionOrder.objects.prefetch_related(
        Prefetch("operations", queryset=Operation.objects.select_related("work_center"))
    )
    if ids is not None:
        qs = qs.filter(id__in=list(ids))
    if active_only:
        qs = qs.exclude(stage=OrderStage.DONE)
    return list(qs.order_by("planned_start", "number"))


def list_operations(
    *,
    ids: Iterable[UUID] | None = None,
    order_id: UUID | None = None,
    work_center_id: UUID | None = None,
    active_orders_only: bool = False,
) -> list[Operation]:
    qs = Operation.objects.select_related("work_center")
    if ids is not None:
        qs = qs.filter(id__in=list(ids))
    if order_id is not None:
        qs = qs.filter(order_id=order_id)
    if work_center_id is not None:
        qs = qs.filter(work_center_id=work_center_id)
    if active_orders_only:
        qs = qs.filter(order__stage__in=(OrderStage.LAUNCH, *WORK_STAGES))
    return list(qs.order_by("order_id", "seq"))


def list_earnings(date_from: date, date_to: date) -> list[tuple[OperationEarning, UUID, UUID]]:
    rows = (
        OperationEarning.objects.filter(date__gte=date_from, date__lte=date_to)
        .select_related("operation")
        .order_by("date", "created_at")
    )
    return [(row, row.operation.order_id, row.operation.work_center_id) for row in rows]
