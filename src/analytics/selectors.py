"""Отчёты аналитики (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8): недельные отсечки,
загрузка 10 недель, портфель по месяцам, выработка сотрудников.

Данные других модулей — только через их фасады (И1); арифметика — в `calculations`.
Число запросов не зависит от числа заказов, операций и сотрудников: фасады отдают
данные пачками, недели и месяцы — фиксированное окно экрана.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from src.analytics import calculations as calc
from src.analytics.calculations import ZERO, SpreadOp
from src.analytics.models import (
    EmployeePeriod,
    PortfolioKind,
    WeeklyCutoff,
    WeeklyCutoffEvent,
    WeekStatus,
)
from src.core.org.models import Employee
from src.production import facade as production
from src.quality import facade as quality
from src.sales import facade as sales
from src.timesheet import facade as timesheet

LOAD_WEEKS = 10
PORTFOLIO_MONTHS = (-2, -1, 0, 1, 2, 3, 4, 5)
EMPLOYEE_MONTHS = 6


def today() -> date:
    return timezone.localdate()


def production_centers() -> list[production.WorkCenterBrief]:
    """Участки, у которых есть часы: снабжение (срок поставки в днях) в отчёты не входит."""

    return [c for c in production.list_work_centers() if not c.is_supply]


# --- План, освоение, контроль по неделям ---------------------------------------------


def _order_operations(date_from: date) -> list[production.OperationBrief]:
    """Операции заказов в работе и отгруженных с `date_from`: план прошлой недели
    включает заказ, который с тех пор отгружен (`planByWeek` берёт все заказы)."""

    orders = production.list_active_orders() + production.list_shipped_orders(date_from, today())
    return production.list_operations_for_orders(o.id for o in orders)


def _plan_ops(ops: Iterable[production.OperationBrief]) -> list[SpreadOp]:
    return [
        SpreadOp(op.work_center_id, op.hours, op.planned_start, op.planned_finish)
        for op in ops
        if not op.is_supply and op.planned_start is not None and op.planned_finish is not None
    ]


def planned_by_week(date_from: date) -> dict[tuple[date, UUID], Decimal]:
    """Плановые н-ч операций заказов по (неделя, участок): вся трудоёмкость операции
    поровну на её рабочие дни (`planByWeek`)."""

    return calc.spread_by_week(_plan_ops(_order_operations(date_from)))


def earned_by_week(date_from: date, date_to: date) -> dict[tuple[date, UUID], Decimal]:
    result: dict[tuple[date, UUID], Decimal] = defaultdict(Decimal)
    for row in production.list_earnings(date_from, date_to):
        result[(calc.week_start(row.date), row.work_center_id)] += row.hours
    return dict(result)


@dataclass(frozen=True)
class QcCell:
    checked: int = 0
    defects: int = 0


def qc_by_week(date_from: date, date_to: date) -> dict[tuple[date, UUID], QcCell]:
    return {
        (row.week_start, row.work_center_id): QcCell(row.checked, row.rework + row.scrap)
        for row in quality.list_qc_by_week(date_from, date_to)
    }


# --- Отсечки -------------------------------------------------------------------------


@dataclass(frozen=True)
class CutoffRow:
    work_center_id: UUID | None  # None — строка «Итого»
    name: str
    capacity: Decimal
    planned: Decimal
    earned: Decimal
    worked: Decimal | None
    checked: int
    defects: int

    @property
    def plan_pct(self) -> Decimal | None:
        return calc.pct(self.earned, self.planned)

    @property
    def output_pct(self) -> Decimal | None:
        return calc.pct(self.earned, self.worked) if self.worked is not None else None

    @property
    def load_pct(self) -> Decimal | None:
        return calc.pct(self.planned, self.capacity)

    @property
    def defect_pct(self) -> Decimal | None:
        return calc.pct(Decimal(self.defects), Decimal(self.checked))


@dataclass(frozen=True)
class CutoffWeek:
    week_start: date
    status: WeekStatus
    closed_by_name: str
    closed_at: datetime | None
    comment: str
    rows: list[CutoffRow]
    total: CutoffRow


def _total(rows: list[CutoffRow]) -> CutoffRow:
    worked = [r.worked for r in rows if r.worked is not None]
    return CutoffRow(
        work_center_id=None,
        name="Итого",
        capacity=sum((r.capacity for r in rows), ZERO),
        planned=sum((r.planned for r in rows), ZERO),
        earned=sum((r.earned for r in rows), ZERO),
        worked=sum(worked, ZERO) if worked else None,
        checked=sum(r.checked for r in rows),
        defects=sum(r.defects for r in rows),
    )


def _capacity(center: production.WorkCenterBrief) -> Decimal:
    return Decimal(center.capacity) * calc.HOURS_PER_WEEK


@dataclass(frozen=True)
class LiveWeekData:
    planned: dict[tuple[date, UUID], Decimal]
    earned: dict[tuple[date, UUID], Decimal]
    qc: dict[tuple[date, UUID], QcCell]


def live_week_data(weeks: list[date]) -> LiveWeekData:
    """Живые данные нескольких недель одним проходом фасадов."""

    if not weeks:
        return LiveWeekData({}, {}, {})
    date_from, date_to = min(weeks), max(weeks) + timedelta(days=6)
    return LiveWeekData(
        planned=planned_by_week(date_from),
        earned=earned_by_week(date_from, date_to),
        qc=qc_by_week(date_from, date_to),
    )


def live_rows(
    week: date,
    centers: list[production.WorkCenterBrief],
    data: LiveWeekData,
    worked: dict[UUID, Decimal] | None,
) -> list[CutoffRow]:
    """Строки открытой недели (`liveWeekRow`); без `worked` — отработано не считалось."""

    rows = []
    for center in centers:
        key = (week, center.id)
        qc = data.qc.get(key, QcCell())
        rows.append(
            CutoffRow(
                work_center_id=center.id,
                name=center.name,
                capacity=_capacity(center),
                planned=calc.hours2(data.planned.get(key, ZERO)),
                earned=calc.hours2(data.earned.get(key, ZERO)),
                worked=calc.hours2(worked.get(center.id, ZERO)) if worked is not None else None,
                checked=qc.checked,
                defects=qc.defects,
            )
        )
    return rows


def worked_by_center(week: date) -> dict[UUID, Decimal]:
    return timesheet.worked_hours_by_work_center(week, week + timedelta(days=6))


def _snapshot_rows(
    cutoff: WeeklyCutoff, centers: list[production.WorkCenterBrief]
) -> list[CutoffRow]:
    by_center = {row.work_center_id: row for row in cutoff.rows.all()}
    names = {c.id: c for c in centers}
    rows = []
    # Порядок — как у участков; участок, которого уже нет в справочнике, всё равно
    # показывается: снимок не теряет строк.
    for wc_id in [c.id for c in centers if c.id in by_center] + [
        wc for wc in by_center if wc not in names
    ]:
        row = by_center[wc_id]
        center = names.get(wc_id)
        rows.append(
            CutoffRow(
                work_center_id=wc_id,
                name=center.name if center else "Участок удалён",
                capacity=_capacity(center) if center else ZERO,
                planned=row.planned_hours,
                earned=row.earned_hours,
                worked=row.worked_hours,
                checked=row.checked,
                defects=row.defects,
            )
        )
    return rows


def get_cutoffs(weeks: list[date]) -> dict[date, WeeklyCutoff]:
    qs = (
        WeeklyCutoff.objects.filter(week_start__in=weeks)
        .select_related("closed_by")
        .prefetch_related("rows")
    )
    return {c.week_start: c for c in qs}


def get_cutoff(week: date) -> WeeklyCutoff | None:
    return WeeklyCutoff.objects.filter(week_start=week).first()


def cutoff_weeks(weeks: list[date], *, worked_for: Iterable[date] = ()) -> list[CutoffWeek]:
    """Недели экрана отсечек: закрытые — из снимка, открытые — живые. Отработанные
    часы открытой недели считаются только для недель из `worked_for`: матрице истории
    они не нужны, а это запрос к табелю на каждую неделю."""

    centers = production_centers()
    cutoffs = get_cutoffs(weeks)
    data = live_week_data([w for w in weeks if w not in cutoffs])
    current = calc.week_start(today())
    worked_weeks = set(worked_for)
    result = []
    for week in weeks:
        cutoff = cutoffs.get(week)
        if cutoff is not None:
            rows = _snapshot_rows(cutoff, centers)
            status = WeekStatus.CLOSED
        else:
            worked = worked_by_center(week) if week in worked_weeks else None
            rows = live_rows(week, centers, data, worked)
            status = WeekStatus.CURRENT if week == current else WeekStatus.OPEN
        result.append(
            CutoffWeek(
                week_start=week,
                status=status,
                closed_by_name=cutoff.closed_by.full_name if cutoff else "",
                closed_at=cutoff.closed_at if cutoff else None,
                comment=cutoff.comment if cutoff else "",
                rows=rows,
                total=_total(rows),
            )
        )
    return result


def list_cutoff_events(week: date) -> list[WeeklyCutoffEvent]:
    return list(
        WeeklyCutoffEvent.objects.filter(week_start=week)
        .select_related("actor")
        .order_by("-created_at")
    )


# --- Загрузка 10 недель (`renderLoad`) ----------------------------------------------


@dataclass(frozen=True)
class LoadCell:
    firm: Decimal
    tentative: Decimal

    @property
    def total(self) -> Decimal:
        return self.firm + self.tentative


@dataclass(frozen=True)
class LoadRow:
    work_center_id: UUID
    name: str
    short_name: str
    capacity: Decimal
    cells: list[LoadCell]


@dataclass(frozen=True)
class LoadGrid:
    weeks: list[date]
    rows: list[LoadRow]


def load_grid() -> LoadGrid:
    """Остаток часов не выполненных операций по участкам на 10 недель: заказы —
    «твёрдо», заявки с предварительным планом — «предварительно». Мощность —
    исполнители × 40 ч в неделю."""

    first = calc.week_start(today())
    weeks = [first + timedelta(weeks=k) for k in range(LOAD_WEEKS)]
    orders = production.list_active_orders()
    firm_ops = [
        SpreadOp(
            op.work_center_id,
            calc.remaining_hours(op.hours, op.progress),
            op.planned_start,
            op.planned_finish,
        )
        for op in production.list_operations_for_orders(o.id for o in orders)
        if not op.is_supply
        and op.status != production.OperationStatus.DONE
        and op.planned_start is not None
        and op.planned_finish is not None
    ]
    tentative_ops = [
        SpreadOp(op.work_center_id, op.hours, op.planned_start, op.planned_finish)
        for item in sales.list_open_inquiries()
        for op in item.operations
        if not op.is_supply and op.planned_start is not None and op.planned_finish is not None
    ]
    firm = calc.spread_by_week(firm_ops)
    tentative = calc.spread_by_week(tentative_ops)
    rows = [
        LoadRow(
            work_center_id=center.id,
            name=center.name,
            short_name=center.short_name,
            capacity=_capacity(center),
            cells=[
                LoadCell(
                    firm=calc.hours2(firm.get((week, center.id), ZERO)),
                    tentative=calc.hours2(tentative.get((week, center.id), ZERO)),
                )
                for week in weeks
            ],
        )
        for center in production_centers()
    ]
    return LoadGrid(weeks=weeks, rows=rows)


# --- Портфель по месяцам (`portfolioData`) -------------------------------------------


@dataclass(frozen=True)
class PortfolioItem:
    id: UUID
    is_order: bool
    number: str
    customer_name: str
    product_name: str
    quantity: Decimal
    stage: str
    month: date
    total: Decimal
    # Вероятность — доля (0…1): заказ 1, заявка — вероятность этапа из настроек sales.
    probability: Decimal
    kind: PortfolioKind
    # Заявка без плана: месяц отгрузки — по требуемому сроку, а не по плану.
    estimated: bool

    @property
    def weighted(self) -> Decimal:
        return self.total * self.probability


@dataclass
class MonthAmounts:
    fact: Decimal = ZERO
    firm: Decimal = ZERO
    pipe: Decimal = ZERO

    def add(self, kind: PortfolioKind, value: Decimal) -> None:
        setattr(self, kind.value, getattr(self, kind.value) + value)

    @property
    def total(self) -> Decimal:
        return self.fact + self.firm + self.pipe


@dataclass(frozen=True)
class PortfolioCenter:
    work_center_id: UUID
    name: str
    short_name: str
    load: list[MonthAmounts]
    capacity: list[Decimal]


@dataclass(frozen=True)
class Portfolio:
    months: list[date]
    current_month: date
    probabilities: dict[str, Decimal]
    revenue: list[MonthAmounts]
    load: list[MonthAmounts]
    capacity: list[Decimal]
    centers: list[PortfolioCenter]
    items: list[PortfolioItem]


def _fact_load(
    months: list[date], until: date, centers: set[UUID]
) -> dict[tuple[date, UUID], Decimal]:
    """Факт освоения по месяцам: закрытые недели — из снимка отсечки (цифры закрытой
    недели не меняются), остальные дни — живое освоение. Неделя снимка относится к месяцу
    своего понедельника, как `monOf(wk)` прототипа."""

    start = months[0]
    first_week = calc.week_start(start)
    weeks = []
    week = first_week
    while week <= until:
        weeks.append(week)
        week += timedelta(weeks=1)
    cutoffs = get_cutoffs(weeks)
    result: dict[tuple[date, UUID], Decimal] = defaultdict(Decimal)
    for cutoff in cutoffs.values():
        if cutoff.week_start < start:
            continue
        for snapshot in cutoff.rows.all():
            if snapshot.work_center_id in centers:
                result[(calc.month_start(cutoff.week_start), snapshot.work_center_id)] += (
                    snapshot.earned_hours
                )
    for earning in production.list_earnings(start, until):
        if calc.week_start(earning.date) in cutoffs or earning.work_center_id not in centers:
            continue
        result[(calc.month_start(earning.date), earning.work_center_id)] += earning.hours
    return dict(result)


def portfolio() -> Portfolio:
    now = today()
    m0 = calc.month_start(now)
    months = [calc.add_months(m0, n) for n in PORTFOLIO_MONTHS]
    centers = production_centers()
    center_ids = {c.id for c in centers}
    index = {m: i for i, m in enumerate(months)}

    items: list[PortfolioItem] = []
    firm_ops: list[SpreadOp] = []
    pipe_ops: list[SpreadOp] = []

    active = production.list_active_orders()
    for order in active:
        finish = order.planned_finish or order.due_date
        items.append(
            PortfolioItem(
                id=order.id,
                is_order=True,
                number=order.number,
                customer_name=order.customer_name,
                product_name=order.product_name,
                quantity=order.quantity,
                stage=order.stage,
                month=max(calc.month_start(finish), m0),
                total=order.contract_total,
                probability=Decimal(1),
                kind=PortfolioKind.FIRM,
                estimated=order.planned_finish is None,
            )
        )
    for op in production.list_operations_for_orders(o.id for o in active):
        if (
            op.is_supply
            or op.status == production.OperationStatus.DONE
            or op.planned_start is None
            or op.planned_finish is None
        ):
            continue
        firm_ops.append(
            SpreadOp(
                op.work_center_id,
                calc.remaining_hours(op.hours, op.progress),
                op.planned_start,
                op.planned_finish,
            )
        )

    for order in production.list_shipped_orders(months[0], now):
        # Отгруженный заказ всегда с датой отгрузки (ограничение БД `production`).
        assert order.shipped_at is not None
        items.append(
            PortfolioItem(
                id=order.id,
                is_order=True,
                number=order.number,
                customer_name=order.customer_name,
                product_name=order.product_name,
                quantity=order.quantity,
                stage=order.stage,
                month=calc.month_start(order.shipped_at),
                total=order.contract_total,
                probability=Decimal(1),
                kind=PortfolioKind.FACT,
                estimated=False,
            )
        )

    for open_inquiry in sales.list_open_inquiries():
        inquiry = open_inquiry.inquiry
        probability = inquiry.probability / calc.HUNDRED
        if probability <= 0:
            continue
        finish = inquiry.planned_finish or inquiry.due_date
        items.append(
            PortfolioItem(
                id=inquiry.id,
                is_order=False,
                number=inquiry.number,
                customer_name=inquiry.customer_name,
                product_name=inquiry.product_name,
                quantity=inquiry.quantity,
                stage=inquiry.stage,
                month=max(calc.month_start(finish), m0),
                total=inquiry.total,
                probability=probability,
                kind=PortfolioKind.PIPE,
                estimated=inquiry.planned_finish is None,
            )
        )
        pipe_ops.extend(
            SpreadOp(op.work_center_id, op.hours * probability, op.planned_start, op.planned_finish)
            for op in open_inquiry.operations
            if not op.is_supply and op.planned_start is not None and op.planned_finish is not None
        )

    revenue = [MonthAmounts() for _ in months]
    for item in items:
        i = index.get(item.month)
        if i is not None:
            revenue[i].add(item.kind, item.weighted)

    layers = {
        PortfolioKind.FACT: _fact_load(months, now, center_ids),
        PortfolioKind.FIRM: calc.spread_by_month(firm_ops, not_before=now),
        PortfolioKind.PIPE: calc.spread_by_month(pipe_ops, not_before=now),
    }
    center_rows = []
    for center in centers:
        load = [MonthAmounts() for _ in months]
        for kind, values in layers.items():
            for i, month in enumerate(months):
                load[i].add(kind, values.get((month, center.id), ZERO))
        center_rows.append(
            PortfolioCenter(
                work_center_id=center.id,
                name=center.name,
                short_name=center.short_name,
                load=load,
                capacity=[
                    Decimal(center.capacity)
                    * calc.HOURS_PER_DAY
                    * calc.working_days_in_month(month)
                    for month in months
                ],
            )
        )
    total_load = [MonthAmounts() for _ in months]
    for row in center_rows:
        for i, amounts in enumerate(row.load):
            for kind in PortfolioKind:
                total_load[i].add(kind, getattr(amounts, kind.value))
    items.sort(key=lambda x: (x.month, -x.total))
    return Portfolio(
        months=months,
        current_month=m0,
        probabilities=sales.get_stage_probabilities(),
        revenue=revenue,
        load=total_load,
        capacity=[sum((r.capacity[i] for r in center_rows), ZERO) for i in range(len(months))],
        centers=center_rows,
        items=items,
    )


# --- Выработка сотрудников (`empStats`) ----------------------------------------------


def period_range(period: EmployeePeriod, now: date | None = None) -> tuple[date, date]:
    """Границы периода (`empPeriod`): по вчерашний день — сегодняшний ещё не разнесён."""

    now = now or today()
    yesterday = now - timedelta(days=1)
    if period == EmployeePeriod.CURRENT_MONTH:
        return calc.month_start(now), yesterday
    if period == EmployeePeriod.PREVIOUS_MONTH:
        previous = calc.add_months(calc.month_start(now), -1)
        return previous, calc.month_end(previous)
    return now - timedelta(days=28), yesterday


@dataclass(frozen=True)
class EmployeeInfo:
    employee_id: UUID
    full_name: str
    position: str
    department_id: UUID
    department_name: str
    work_center_id: UUID
    work_center_short: str
    hourly_rate: Decimal


@dataclass(frozen=True)
class EmployeeMonth:
    month: date
    rub: Decimal
    cost: Decimal


@dataclass(frozen=True)
class EmployeeRow:
    info: EmployeeInfo
    stats: calc.EmployeeStats
    months: list[EmployeeMonth]


@dataclass(frozen=True)
class Department:
    id: UUID
    name: str


@dataclass(frozen=True)
class EmployeesReport:
    date_from: date
    date_to: date
    months: list[date]
    departments: list[Department]
    rows: list[EmployeeRow]
    # Итог по строкам отчёта (с учётом фильтра подразделения).
    total: calc.EmployeeStats
    total_earned: Decimal
    unattributed: Decimal


@dataclass(frozen=True)
class _StatsInput:
    allocations: list[calc.Allocation]
    earnings: list[production.EarningRow]
    rates: dict[UUID, Decimal]


def _employees() -> list[EmployeeInfo]:
    """Работники с участком (`r.e.wc` прототипа): у остальных нет освоения."""

    profiles = [p for p in timesheet.get_worker_profiles() if p.work_center_id is not None]
    employees = {
        e.id: e
        for e in Employee.objects.filter(id__in=[p.employee_id for p in profiles]).select_related(
            "position", "department"
        )
    }
    centers = {c.id: c for c in production.list_work_centers()}
    result = []
    for p in profiles:
        employee = employees.get(p.employee_id)
        assert p.work_center_id is not None
        center = centers.get(p.work_center_id)
        result.append(
            EmployeeInfo(
                employee_id=p.employee_id,
                full_name=p.full_name,
                position=employee.position.name if employee else "",
                department_id=p.department_id,
                department_name=employee.department.name if employee else "",
                work_center_id=p.work_center_id,
                work_center_short=center.short_name if center else "",
                hourly_rate=p.hourly_rate,
            )
        )
    result.sort(key=lambda e: e.full_name)
    return result


def _stats_input(date_from: date, date_to: date) -> _StatsInput:
    allocations = [
        calc.Allocation(
            employee_id=a.employee_id,
            date=a.date,
            is_work=a.is_work,
            cost_multiplier=a.cost_multiplier,
            target=a.target,
            operation_id=a.operation_id,
            hours=a.hours,
            hourly_rate=a.hourly_rate,
        )
        for a in timesheet.list_allocations(date_from, date_to)
    ]
    rates = {c.id: c.rate for c in production.list_work_centers()}
    return _StatsInput(allocations, production.list_earnings(date_from, date_to), rates)


def _stats_for(
    data: _StatsInput,
    date_from: date,
    date_to: date,
    qc: dict[UUID, calc.OperationQc],
) -> calc.EmployeeStatsResult:
    earned: dict[UUID, Decimal] = defaultdict(Decimal)
    rate_by_operation: dict[UUID, Decimal] = {}
    for row in data.earnings:
        if date_from <= row.date <= date_to:
            earned[row.operation_id] += row.hours
            rate_by_operation[row.operation_id] = data.rates.get(row.work_center_id, ZERO)
    return calc.employee_stats(
        (a for a in data.allocations if date_from <= a.date <= date_to),
        earned,
        rate_by_operation,
        qc,
    )


def _qc(date_from: date, date_to: date) -> dict[UUID, calc.OperationQc]:
    return {
        op_id: calc.OperationQc(agg.checked, agg.defects, agg.operator_defects)
        for op_id, agg in quality.list_qc_by_operation(date_from, date_to).items()
    }


_SUMMED = (
    "worked",
    "on_orders",
    "overhead",
    "idle",
    "repair",
    "training",
    "overtime",
    "absent_days",
    "earned",
    "checked",
    "defects",
    "operator_defects",
    "rub",
    "cost",
)


def _sum_stats(items: Iterable[calc.EmployeeStats]) -> calc.EmployeeStats:
    total = calc.EmployeeStats()
    for stats in items:
        for name in _SUMMED:
            setattr(total, name, getattr(total, name) + getattr(stats, name))
    return total


def employees_report(period: EmployeePeriod, department_id: UUID | None) -> EmployeesReport:
    now = today()
    date_from, date_to = period_range(period, now)
    m0 = calc.month_start(now)
    months = [calc.add_months(m0, n) for n in range(1 - EMPLOYEE_MONTHS, 1)]
    yesterday = now - timedelta(days=1)
    data = _stats_input(min(date_from, months[0]), max(date_to, yesterday))
    period_stats = _stats_for(data, date_from, date_to, _qc(date_from, date_to))
    monthly = [
        _stats_for(data, m, min(calc.month_end(m), yesterday), {}).by_employee for m in months
    ]
    all_employees = _employees()
    departments = sorted(
        {Department(e.department_id, e.department_name) for e in all_employees},
        key=lambda d: d.name,
    )
    infos = (
        all_employees
        if department_id is None
        else [e for e in all_employees if e.department_id == department_id]
    )
    rows = [
        EmployeeRow(
            info=info,
            stats=period_stats.by_employee.get(info.employee_id, calc.EmployeeStats()),
            months=[
                EmployeeMonth(
                    month=m,
                    rub=stats.get(info.employee_id, calc.EmployeeStats()).rub,
                    cost=stats.get(info.employee_id, calc.EmployeeStats()).cost,
                )
                for m, stats in zip(months, monthly, strict=True)
            ],
        )
        for info in infos
    ]
    return EmployeesReport(
        date_from=date_from,
        date_to=date_to,
        months=months,
        departments=departments,
        rows=rows,
        total=_sum_stats(row.stats for row in rows),
        total_earned=period_stats.total_earned,
        unattributed=period_stats.unattributed,
    )


@dataclass(frozen=True)
class EmployeeOperation:
    operation_id: UUID
    order_id: UUID
    order_number: str
    operation_name: str
    norm_hours: Decimal
    status: str
    share: calc.OperationShare


@dataclass(frozen=True)
class EmployeeCard:
    info: EmployeeInfo
    date_from: date
    date_to: date
    stats: calc.EmployeeStats
    operations: list[EmployeeOperation]


def employee_card(employee_id: UUID, period: EmployeePeriod) -> EmployeeCard | None:
    info = next((e for e in _employees() if e.employee_id == employee_id), None)
    if info is None:
        return None
    date_from, date_to = period_range(period)
    data = _stats_input(date_from, date_to)
    stats = _stats_for(data, date_from, date_to, _qc(date_from, date_to)).by_employee.get(
        employee_id, calc.EmployeeStats()
    )
    operations = production.get_operations_brief(stats.operations.keys())
    orders = production.get_orders_brief({op.order_id for op in operations.values()})
    rows = [
        EmployeeOperation(
            operation_id=op_id,
            order_id=op.order_id,
            order_number=orders[op.order_id].number if op.order_id in orders else "",
            operation_name=op.name,
            norm_hours=op.hours,
            status=op.status,
            share=share,
        )
        for op_id, share in stats.operations.items()
        if (op := operations.get(op_id)) is not None
    ]
    rows.sort(key=lambda r: -r.share.hours)
    return EmployeeCard(
        info=info, date_from=date_from, date_to=date_to, stats=stats, operations=rows
    )
