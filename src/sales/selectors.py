"""Запросы на чтение модуля «Заявки и калькуляция»: доска, карточка с калькуляцией и
предварительным планом, «Мои визы», данные для портфеля
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2, §6).

Участки (ставка, снабжение) читаются через `production.facade` один раз на запрос.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db.models import F, Prefetch, Q, QuerySet

from src.core.common.scheduling import (
    HealthColor,
    ScheduleAnalysis,
    analyze,
    assess_health,
    compute_schedule,
    next_working_day,
    working_days_between,
)
from src.core.org.models import Employee
from src.sales.calculations import CalcTotals, LaborLine, MaterialLine, calc_totals
from src.sales.models import (
    OPEN_STAGES,
    CalcMaterial,
    CalcOperation,
    CalcOperationDependency,
    Inquiry,
    InquiryStage,
    InquiryStageApproval,
    LossReason,
    SalesSettings,
)
from src.sales.planning import Centers, centers_by_id, duration_of, finish_of, is_supply, network


def _name(employee: Employee | None) -> str:
    return employee.full_name if employee is not None else ""


def lines_for_totals(
    materials: Iterable[CalcMaterial], operations: Iterable[CalcOperation], centers: Centers
) -> tuple[list[MaterialLine], list[LaborLine]]:
    material_lines = [MaterialLine(quantity=m.quantity, price=m.price) for m in materials]
    labor_lines = []
    for op in operations:
        center = centers.get(op.work_center_id)
        labor_lines.append(
            LaborLine(
                hours=op.hours,
                rate=center.rate if center else Decimal("0"),
                is_supply=bool(center and center.is_supply),
            )
        )
    return material_lines, labor_lines


def _totals(inquiry: Inquiry, centers: Centers) -> CalcTotals:
    materials, labor = lines_for_totals(inquiry.materials.all(), inquiry.operations.all(), centers)
    return calc_totals(
        materials,
        labor,
        overhead_pct=inquiry.overhead_pct,
        margin_pct=inquiry.margin_pct,
        vat_pct=inquiry.vat_pct,
    )


def get_settings() -> SalesSettings | None:
    return SalesSettings.objects.select_related("economist").first()


def _probabilities() -> dict[str, Decimal]:
    settings = get_settings()
    if settings is None:
        return {
            InquiryStage.NEW: Decimal("10"),
            InquiryStage.CALC: Decimal("30"),
            InquiryStage.APPROVAL: Decimal("60"),
        }
    return {
        InquiryStage.NEW: settings.prob_new,
        InquiryStage.CALC: settings.prob_calc,
        InquiryStage.APPROVAL: settings.prob_approval,
    }


def stage_probabilities() -> dict[str, Decimal]:
    return _probabilities()


def list_loss_reasons() -> list[LossReason]:
    return list(LossReason.objects.filter(is_active=True))


# --- Доска -------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthView:
    color: str
    status: str
    days: int
    text: str


def _health(inquiry: Inquiry, operations: Sequence[CalcOperation], centers: Centers) -> HealthView:
    finishes = [finish_of(op, centers) for op in operations]
    has_plan = bool(operations) and all(f is not None for f in finishes)
    finish = max((f for f in finishes if f is not None), default=None)
    health = assess_health(
        finish=finish, due=inquiry.due_date, has_plan=has_plan, is_done=False, is_lagging=False
    )
    texts = {
        "no_plan": "Нет плана",
        "late": f"Не укладываемся на {health.days} дн.",
        "tight": f"Запас {health.days} дн.",
        "ok": "Укладываемся",
    }
    return HealthView(
        color=HealthColor(health.color).value,
        status=health.status,
        days=health.days,
        text=texts.get(health.status, ""),
    )


@dataclass(frozen=True)
class InquiryCard:
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
    stage: str
    health: HealthView
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


def _inquiries() -> QuerySet[Inquiry]:
    return Inquiry.objects.select_related("manager", "lost_reason").prefetch_related(
        "materials",
        Prefetch("operations", queryset=CalcOperation.objects.order_by("seq")),
        Prefetch(
            "stage_approvals",
            queryset=InquiryStageApproval.objects.select_related("responsible", "approved_by"),
        ),
    )


def _card(inquiry: Inquiry, centers: Centers, probabilities: dict[str, Decimal]) -> InquiryCard:
    operations = list(inquiry.operations.all())
    finishes = [finish_of(op, centers) for op in operations]
    current = next((a for a in inquiry.stage_approvals.all() if a.stage == inquiry.stage), None)
    return InquiryCard(
        id=inquiry.id,
        number=inquiry.number,
        customer_id=inquiry.customer_id,
        customer_name=inquiry.customer_name,
        object_name=inquiry.object_name,
        template_id=inquiry.template_id,
        product_name=inquiry.product_name,
        quantity=inquiry.quantity,
        due_date=inquiry.due_date,
        manager_id=inquiry.manager_id,
        manager_name=_name(inquiry.manager),
        stage=inquiry.stage,
        health=_health(inquiry, operations, centers),
        total=_totals(inquiry, centers).total,
        probability=probabilities.get(inquiry.stage, Decimal("0")),
        stage_responsible_id=current.responsible_id if current else None,
        stage_responsible_name=_name(current.responsible) if current else "",
        stage_approved=bool(current and current.approved_at is not None),
        planned_start=inquiry.planned_start,
        planned_finish=max((f for f in finishes if f is not None), default=None),
        has_calc=bool(operations) or bool(list(inquiry.materials.all())),
        has_plan=bool(operations) and all(f is not None for f in finishes),
        order_id=inquiry.order_id,
    )


def list_board(
    *, stage: InquiryStage | None = None, search: str = "", include_closed: bool = False
) -> list[InquiryCard]:
    """Карточки заявок — фиксированное число запросов независимо от их числа."""

    qs = _inquiries().order_by("due_date", "number")
    if stage is not None:
        qs = qs.filter(stage=stage)
    elif not include_closed:
        qs = qs.filter(stage__in=OPEN_STAGES)
    if search.strip():
        term = search.strip()
        qs = qs.filter(
            Q(number__icontains=term)
            | Q(customer_name__icontains=term)
            | Q(object_name__icontains=term)
            | Q(product_name__icontains=term)
        )
    centers = centers_by_id()
    probabilities = _probabilities()
    return [_card(inquiry, centers, probabilities) for inquiry in qs]


# --- Карточка ----------------------------------------------------------------------


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
class MaterialRow:
    id: UUID
    name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class CalcOperationRow:
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


@dataclass(frozen=True)
class TotalsView:
    materials: Decimal
    labor: Decimal
    hours: Decimal
    overhead: Decimal
    cost: Decimal
    price: Decimal
    vat: Decimal
    total: Decimal
    profit: Decimal


@dataclass(frozen=True)
class InquiryDetail(InquiryCard):
    overhead_pct: Decimal
    margin_pct: Decimal
    vat_pct: Decimal
    lost_reason_id: UUID | None
    lost_reason_name: str
    lost_comment: str
    created_at: datetime
    approvals: list[StageApprovalView]
    materials: list[MaterialRow]
    operations: list[CalcOperationRow]
    totals: TotalsView
    plan_length: int
    critical_path: list[UUID]


def _analysis(
    operations: Sequence[CalcOperation],
    dependencies: Sequence[CalcOperationDependency],
    centers: Centers,
) -> ScheduleAnalysis | None:
    if not operations or any(op.planned_start is None for op in operations):
        return None
    nodes, edges = network(operations, dependencies, centers)
    starts = {op.id: op.planned_start for op in operations if op.planned_start is not None}
    return analyze(nodes, edges, starts)


def get_inquiry(inquiry_id: UUID) -> Inquiry | None:
    return Inquiry.objects.filter(id=inquiry_id).first()


def get_inquiry_detail(inquiry_id: UUID) -> InquiryDetail | None:
    inquiry = _inquiries().filter(id=inquiry_id).first()
    if inquiry is None:
        return None
    centers = centers_by_id()
    card = _card(inquiry, centers, _probabilities())
    operations = list(inquiry.operations.all())
    dependencies = list(CalcOperationDependency.objects.filter(successor__inquiry=inquiry))
    analysis = _analysis(operations, dependencies, centers)
    preds: dict[UUID, list[UUID]] = defaultdict(list)
    for dep in dependencies:
        preds[dep.successor_id].append(dep.predecessor_id)
    order_index = {stage: i for i, stage in enumerate(InquiryStage.values)}
    approvals = sorted(inquiry.stage_approvals.all(), key=lambda a: order_index[a.stage])
    totals = _totals(inquiry, centers)
    rows = []
    for op in operations:
        center = centers.get(op.work_center_id)
        node = analysis.nodes.get(op.id) if analysis else None
        rows.append(
            CalcOperationRow(
                id=op.id,
                seq=op.seq,
                name=op.name,
                work_center_id=op.work_center_id,
                work_center_short_name=center.short_name if center else "",
                work_center_name=center.name if center else "",
                is_supply=is_supply(op, centers),
                capacity=center.capacity if center else 1,
                rate=center.rate if center else Decimal("0"),
                hours=op.hours,
                people=op.people,
                duration=duration_of(op, centers),
                not_before=op.not_before,
                planned_start=op.planned_start,
                planned_finish=finish_of(op, centers),
                predecessor_ids=preds.get(op.id, []),
                slack=node.slack if node else None,
                is_critical=bool(node and node.is_critical),
            )
        )
    return InquiryDetail(
        **card.__dict__,
        overhead_pct=inquiry.overhead_pct,
        margin_pct=inquiry.margin_pct,
        vat_pct=inquiry.vat_pct,
        lost_reason_id=inquiry.lost_reason_id,
        lost_reason_name=inquiry.lost_reason.name if inquiry.lost_reason else "",
        lost_comment=inquiry.lost_comment,
        created_at=inquiry.created_at,
        approvals=[
            StageApprovalView(
                stage=a.stage,
                stage_label=str(InquiryStage(a.stage).label),
                responsible_id=a.responsible_id,
                responsible_name=_name(a.responsible),
                approved_by_id=a.approved_by_id,
                approved_by_name=_name(a.approved_by),
                approved_at=a.approved_at,
                comment=a.comment,
            )
            for a in approvals
        ],
        materials=[
            MaterialRow(
                id=m.id,
                name=m.name,
                quantity=m.quantity,
                price=m.price,
                amount=(m.quantity * m.price).quantize(Decimal("0.0001")),
            )
            for m in sorted(inquiry.materials.all(), key=lambda m: (m.sort_order, m.created_at))
        ],
        operations=rows,
        totals=TotalsView(**totals.__dict__),
        plan_length=analysis.length if analysis else 0,
        critical_path=analysis.critical_path if analysis else [],
    )


def get_stage_approval(inquiry_id: UUID, stage: str) -> InquiryStageApproval | None:
    return InquiryStageApproval.objects.filter(inquiry_id=inquiry_id, stage=stage).first()


def inquiry_id_of_material(material_id: UUID) -> UUID | None:
    return CalcMaterial.objects.filter(id=material_id).values_list("inquiry_id", flat=True).first()


def inquiry_id_of_operation(operation_id: UUID) -> UUID | None:
    return (
        CalcOperation.objects.filter(id=operation_id).values_list("inquiry_id", flat=True).first()
    )


# --- «Мои визы» --------------------------------------------------------------------


@dataclass(frozen=True)
class VisaItem:
    inquiry_id: UUID
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    due_date: date
    stage: str
    text: str


def list_my_visas(employee_id: UUID) -> list[VisaItem]:
    """Текущие этапы заявок, где я ответственный и визы нет (`myVisaList` прототипа:
    этап «Новые» не в счёт)."""

    approvals = (
        InquiryStageApproval.objects.filter(
            responsible_id=employee_id, approved_at__isnull=True, stage=F("inquiry__stage")
        )
        .exclude(stage=InquiryStage.NEW)
        .select_related("inquiry")
        .order_by("inquiry__due_date", "inquiry__number")
    )
    return [
        VisaItem(
            inquiry_id=a.inquiry_id,
            number=a.inquiry.number,
            customer_name=a.inquiry.customer_name,
            product_name=a.inquiry.product_name,
            quantity=a.inquiry.quantity,
            due_date=a.inquiry.due_date,
            stage=a.stage,
            text=f"Этап «{InquiryStage(a.stage).label}»",
        )
        for a in approvals
    ]


# --- Предпросмотр запуска ----------------------------------------------------------


@dataclass(frozen=True)
class LaunchPreview:
    planned_start: date
    planned_finish: date | None
    length: int
    # Положительное — позже срока на столько рабочих дней, отрицательное — запас.
    days_late: int
    critical_path: list[str]


def launch_preview(inquiry_id: UUID, planned_start: date, due_date: date) -> LaunchPreview | None:
    """Расчётное окончание и критический путь заказа, который получится при запуске
    с `planned_start` (`launchDialog` прототипа). Ничего не сохраняет: диалог пересчитывает
    при каждой смене даты, а план заявки должен остаться прежним до подтверждения."""

    inquiry = get_inquiry(inquiry_id)
    if inquiry is None:
        return None
    start = next_working_day(planned_start)
    operations = list(CalcOperation.objects.filter(inquiry=inquiry).order_by("seq"))
    if not operations:
        return LaunchPreview(
            planned_start=start, planned_finish=None, length=0, days_late=0, critical_path=[]
        )
    dependencies = list(CalcOperationDependency.objects.filter(successor__inquiry=inquiry))
    nodes, edges = network(operations, dependencies, centers_by_id())
    analysis = compute_schedule(nodes, edges, base=start)
    names = {op.id: op.name for op in operations}
    finish = analysis.finish
    return LaunchPreview(
        planned_start=start,
        planned_finish=finish,
        length=analysis.length,
        days_late=working_days_between(due_date, finish) if finish else 0,
        critical_path=[names[op_id] for op_id in analysis.critical_path],
    )


# --- Для фасада --------------------------------------------------------------------


@dataclass(frozen=True)
class PlanOperation:
    work_center_id: UUID
    hours: Decimal
    is_supply: bool
    planned_start: date | None
    planned_finish: date | None


@dataclass(frozen=True)
class InquiryWithPlan:
    card: InquiryCard
    operations: list[PlanOperation]


def list_inquiries_with_plan(
    *, ids: Iterable[UUID] | None = None, open_only: bool = False
) -> list[InquiryWithPlan]:
    qs = _inquiries()
    if ids is not None:
        qs = qs.filter(id__in=list(ids))
    if open_only:
        qs = qs.filter(stage__in=OPEN_STAGES)
    centers = centers_by_id()
    probabilities = _probabilities()
    result = []
    for inquiry in qs.order_by("number"):
        result.append(
            InquiryWithPlan(
                card=_card(inquiry, centers, probabilities),
                operations=[
                    PlanOperation(
                        work_center_id=op.work_center_id,
                        hours=op.hours,
                        is_supply=is_supply(op, centers),
                        planned_start=op.planned_start,
                        planned_finish=finish_of(op, centers),
                    )
                    for op in inquiry.operations.all()
                ],
            )
        )
    return result
