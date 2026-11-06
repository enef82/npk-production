"""Эндпоинты django-ninja модуля «Аналитика» — экраны «Отсечки», «Загрузка участков»,
«Портфель», «Сотрудники» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8, §6;
прототип `renderPerf`, `renderLoad`, `renderPortfolio`, `empPanel`).

Чтение — любой аутентифицированный. Закрытие и переоткрытие отсечки — держатель
`analytics.close_cutoff` (проверка здесь, сервис проверяет правила недели); экран
получает `abilities`, посчитанные той же функцией.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.http import Http404, HttpRequest
from ninja import Query, Router

from src.analytics import calculations as calc
from src.analytics import rules, selectors
from src.analytics.exceptions import ActorNotEmployee, NotMonday
from src.analytics.models import CutoffAction, WeekStatus
from src.analytics.services import cutoff as cutoff_services
from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.production import facade as production
from src.sales import facade as sales

from .filters import AnalyticsCutoffFilters, AnalyticsEmployeeCardFilters, AnalyticsEmployeeFilters
from .schemas import (
    AnalyticsCloseCutoffIn,
    AnalyticsCutoffAbilitiesOut,
    AnalyticsCutoffActionOut,
    AnalyticsCutoffEventOut,
    AnalyticsCutoffRowOut,
    AnalyticsCutoffsOut,
    AnalyticsCutoffWeekOut,
    AnalyticsDepartmentOut,
    AnalyticsEmployeeCardOut,
    AnalyticsEmployeeMonthOut,
    AnalyticsEmployeeOperationOut,
    AnalyticsEmployeeRowOut,
    AnalyticsEmployeesOut,
    AnalyticsEmployeeStatsOut,
    AnalyticsEmployeeWeekOut,
    AnalyticsLoadCellOut,
    AnalyticsLoadOut,
    AnalyticsLoadRowOut,
    AnalyticsMonthAmountsOut,
    AnalyticsMonthLoadOut,
    AnalyticsPortfolioCenterOut,
    AnalyticsPortfolioItemOut,
    AnalyticsPortfolioOut,
    AnalyticsReopenCutoffIn,
    AnalyticsStageProbabilityOut,
)

router = Router(tags=["analytics"])

CLOSE_DENIED = "Отсечку недели закрывает и переоткрывает начальник производства."


class AuthenticatedHttpRequest(HttpRequest):
    auth: User


def _actor(user: User) -> UUID:
    if not rules.can_close_cutoff(user):
        raise PermissionDenied(CLOSE_DENIED)
    employee_id = rules.employee_id_of(user)
    if employee_id is None:
        raise ActorNotEmployee
    return employee_id


# --- Отсечки -------------------------------------------------------------------------


def _row_out(row: selectors.CutoffRow) -> AnalyticsCutoffRowOut:
    return AnalyticsCutoffRowOut(
        work_center_id=row.work_center_id,
        name=row.name,
        capacity=row.capacity,
        planned=row.planned,
        earned=row.earned,
        worked=row.worked,
        plan_pct=row.plan_pct,
        output_pct=row.output_pct,
        load_pct=row.load_pct,
        checked=row.checked,
        defects=row.defects,
        defect_pct=row.defect_pct,
    )


def _week_out(week: selectors.CutoffWeek) -> AnalyticsCutoffWeekOut:
    return AnalyticsCutoffWeekOut(
        week_start=week.week_start,
        status=week.status,
        closed_by_name=week.closed_by_name,
        closed_at=week.closed_at,
        comment=week.comment,
        rows=[_row_out(r) for r in week.rows],
        total=_row_out(week.total),
    )


@router.get("/cutoffs", response=AnalyticsCutoffsOut, operation_id="getAnalyticsCutoffs")
def get_cutoffs(
    request: AuthenticatedHttpRequest, filters: Query[AnalyticsCutoffFilters]
) -> AnalyticsCutoffsOut:
    current = calc.week_start(selectors.today())
    weeks = [current - timedelta(weeks=k) for k in range(filters.weeks - 1, -1, -1)]
    selected = filters.week or current
    if selected.weekday() != 0:
        raise NotMonday
    if selected > current:
        raise Http404
    if selected < weeks[0]:
        # Неделя старше окна — окно истории сдвигается так, чтобы закончиться на ней.
        weeks = [selected - timedelta(weeks=k) for k in range(filters.weeks - 1, -1, -1)]
    return AnalyticsCutoffsOut(
        current_week=current,
        selected_week=selected,
        weeks=[_week_out(w) for w in selectors.cutoff_weeks(weeks, worked_for=[selected])],
        events=[
            AnalyticsCutoffEventOut(
                action=event.action,
                action_label=CutoffAction(event.action).label,
                actor_name=event.actor.full_name,
                created_at=event.created_at,
                text=event.text,
            )
            for event in selectors.list_cutoff_events(selected)
        ],
        abilities=AnalyticsCutoffAbilitiesOut(can_close=bool(rules.can_close_cutoff(request.auth))),
    )


@router.post("/cutoffs", response=AnalyticsCutoffActionOut, operation_id="closeAnalyticsCutoff")
def close_cutoff(
    request: AuthenticatedHttpRequest, payload: AnalyticsCloseCutoffIn
) -> AnalyticsCutoffActionOut:
    actor_id = _actor(request.auth)
    cutoff_services.close_week(
        payload.week_start,
        actor_employee_id=actor_id,
        comment=payload.comment,
        worked_hours={row.work_center_id: row.hours for row in payload.worked},
    )
    return AnalyticsCutoffActionOut(week_start=payload.week_start, status=WeekStatus.CLOSED)


@router.post(
    "/cutoffs/{week_start}/reopen",
    response=AnalyticsCutoffActionOut,
    operation_id="reopenAnalyticsCutoff",
)
def reopen_cutoff(
    request: AuthenticatedHttpRequest, week_start: date, payload: AnalyticsReopenCutoffIn
) -> AnalyticsCutoffActionOut:
    actor_id = _actor(request.auth)
    cutoff_services.reopen_week(week_start, actor_employee_id=actor_id, reason=payload.reason)
    current = calc.week_start(selectors.today())
    status = WeekStatus.CURRENT if week_start == current else WeekStatus.OPEN
    return AnalyticsCutoffActionOut(week_start=week_start, status=status)


# --- Загрузка 10 недель --------------------------------------------------------------


@router.get("/load", response=AnalyticsLoadOut, operation_id="getAnalyticsLoad")
def get_load(request: HttpRequest) -> AnalyticsLoadOut:
    grid = selectors.load_grid()
    return AnalyticsLoadOut(
        weeks=grid.weeks,
        rows=[
            AnalyticsLoadRowOut(
                work_center_id=row.work_center_id,
                name=row.name,
                short_name=row.short_name,
                capacity=row.capacity,
                cells=[
                    AnalyticsLoadCellOut(
                        firm=cell.firm,
                        tentative=cell.tentative,
                        total=cell.total,
                        pct=calc.pct(cell.total, row.capacity),
                    )
                    for cell in row.cells
                ],
            )
            for row in grid.rows
        ],
    )


# --- Портфель ------------------------------------------------------------------------


def _amounts_out(m: selectors.MonthAmounts) -> AnalyticsMonthAmountsOut:
    return AnalyticsMonthAmountsOut(
        fact=calc.hours2(m.fact),
        firm=calc.hours2(m.firm),
        pipe=calc.hours2(m.pipe),
        total=calc.hours2(m.total),
    )


def _load_out(m: selectors.MonthAmounts, capacity: Decimal) -> AnalyticsMonthLoadOut:
    return AnalyticsMonthLoadOut(
        fact=calc.hours2(m.fact),
        firm=calc.hours2(m.firm),
        pipe=calc.hours2(m.pipe),
        total=calc.hours2(m.total),
        capacity=capacity,
        pct=calc.pct(m.total, capacity),
        pipe_pct=calc.pct(m.pipe, capacity),
    )


def _stage_label(item: selectors.PortfolioItem) -> str:
    if item.is_order:
        return str(production.OrderStage(item.stage).label)
    return str(sales.InquiryStage(item.stage).label)


@router.get("/portfolio", response=AnalyticsPortfolioOut, operation_id="getAnalyticsPortfolio")
def get_portfolio(request: HttpRequest) -> AnalyticsPortfolioOut:
    data = selectors.portfolio()
    return AnalyticsPortfolioOut(
        months=data.months,
        current_month=data.current_month,
        probabilities=[
            AnalyticsStageProbabilityOut(
                stage=stage, label=str(sales.InquiryStage(stage).label), probability=value
            )
            for stage, value in data.probabilities.items()
        ],
        revenue=[_amounts_out(m) for m in data.revenue],
        load=[_load_out(m, cap) for m, cap in zip(data.load, data.capacity, strict=True)],
        centers=[
            AnalyticsPortfolioCenterOut(
                work_center_id=c.work_center_id,
                name=c.name,
                short_name=c.short_name,
                months=[_load_out(m, cap) for m, cap in zip(c.load, c.capacity, strict=True)],
            )
            for c in data.centers
        ],
        items=[
            AnalyticsPortfolioItemOut(
                id=item.id,
                is_order=item.is_order,
                number=item.number,
                customer_name=item.customer_name,
                product_name=item.product_name,
                quantity=item.quantity,
                stage=item.stage,
                stage_label=_stage_label(item),
                month=item.month,
                total=calc.hours2(item.total),
                probability_pct=calc.hours2(item.probability * calc.HUNDRED),
                weighted=calc.hours2(item.weighted),
                kind=item.kind,
                estimated=item.estimated,
            )
            for item in data.items
        ],
    )


# --- Сотрудники ----------------------------------------------------------------------


def _stats_out(s: calc.EmployeeStats) -> AnalyticsEmployeeStatsOut:
    h = calc.hours2
    return AnalyticsEmployeeStatsOut(
        worked=h(s.worked),
        on_orders=h(s.on_orders),
        overhead=h(s.overhead),
        idle=h(s.idle),
        repair=h(s.repair),
        training=h(s.training),
        overtime=h(s.overtime),
        absent_days=h(s.absent_days),
        earned=h(s.earned),
        output_pct=calc.pct(s.earned, s.on_orders),
        use_pct=calc.pct(s.on_orders, s.worked),
        productivity_pct=calc.pct(s.earned, s.worked),
        checked=h(s.checked),
        defects=h(s.defects),
        operator_defects=h(s.operator_defects),
        defect_pct=calc.pct(s.defects, s.checked),
        rub=h(s.rub),
        cost=h(s.cost),
        return_ratio=calc.ratio(s.rub, s.cost),
        rub_per_hour=calc.ratio(s.rub, s.worked),
        contribution=h(s.rub - s.cost),
    )


@router.get("/employees", response=AnalyticsEmployeesOut, operation_id="getAnalyticsEmployees")
def get_employees(
    request: HttpRequest, filters: Query[AnalyticsEmployeeFilters]
) -> AnalyticsEmployeesOut:
    report = selectors.employees_report(filters.period, filters.department_id)
    return AnalyticsEmployeesOut(
        period=filters.period,
        date_from=report.date_from,
        date_to=report.date_to,
        months=report.months,
        departments=[AnalyticsDepartmentOut(id=d.id, name=d.name) for d in report.departments],
        total=_stats_out(report.total),
        unattributed=calc.hours2(report.unattributed),
        rows=[
            AnalyticsEmployeeRowOut(
                employee_id=row.info.employee_id,
                full_name=row.info.full_name,
                position=row.info.position,
                department_id=row.info.department_id,
                department_name=row.info.department_name,
                work_center_short=row.info.work_center_short,
                hourly_rate=row.info.hourly_rate,
                stats=_stats_out(row.stats),
                months=[
                    AnalyticsEmployeeMonthOut(
                        month=m.month,
                        rub=calc.hours2(m.rub),
                        cost=calc.hours2(m.cost),
                        return_ratio=calc.ratio(m.rub, m.cost),
                    )
                    for m in row.months
                ],
            )
            for row in report.rows
        ],
    )


@router.get(
    "/employees/{employee_id}",
    response=AnalyticsEmployeeCardOut,
    operation_id="getAnalyticsEmployee",
)
def get_employee(
    request: HttpRequest, employee_id: UUID, filters: Query[AnalyticsEmployeeCardFilters]
) -> AnalyticsEmployeeCardOut:
    card = selectors.employee_card(employee_id, filters.period)
    if card is None:
        raise Http404
    h = calc.hours2
    return AnalyticsEmployeeCardOut(
        employee_id=card.info.employee_id,
        full_name=card.info.full_name,
        position=card.info.position,
        department_name=card.info.department_name,
        work_center_short=card.info.work_center_short,
        hourly_rate=card.info.hourly_rate,
        period=filters.period,
        date_from=card.date_from,
        date_to=card.date_to,
        stats=_stats_out(card.stats),
        weeks=[
            AnalyticsEmployeeWeekOut(
                week_start=week,
                hours=h(w.hours),
                earned=h(w.earned),
                rub=h(w.rub),
                cost=h(w.cost),
                productivity_pct=calc.pct(w.earned, w.hours),
            )
            for week, w in sorted(card.stats.weeks.items())
        ],
        operations=[
            AnalyticsEmployeeOperationOut(
                operation_id=op.operation_id,
                order_id=op.order_id,
                order_number=op.order_number,
                operation_name=op.operation_name,
                norm_hours=op.norm_hours,
                status=op.status,
                hours=h(op.share.hours),
                earned=h(op.share.earned),
                rub=h(op.share.rub),
                output_pct=calc.pct(op.share.earned, op.share.hours),
            )
            for op in card.operations
        ],
    )
