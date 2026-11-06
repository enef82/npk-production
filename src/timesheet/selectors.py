"""Запросы на чтение и агрегаты модуля «Табель».

Свод табеля (сотрудник × день → код/часы), итоги по видам времени и объектам,
проверки и часы по заказам менеджеров — производные разноски (И7), здесь, а не в
хранимых таблицах. Сетка месяца — постоянное число запросов при любом числе людей.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import QuerySet

from src.core.org.models import Department
from src.timesheet.calculations import (
    DAY_NORM,
    OVERTIME_CODE,
    TRIP_CODE,
    AllocationFact,
    Check,
    CheckWorker,
    PackageFact,
    analytics_for,
    build_packages,
    compute_checks,
    is_weekend,
    last_closed_day,
    month_days,
    month_start,
    working_days_until,
)
from src.timesheet.models import (
    AllocationTarget,
    PeriodEventKind,
    PeriodStatus,
    TimeCode,
    TimesheetPeriod,
    TimesheetPeriodEvent,
    WorkAllocation,
    WorkerProfile,
)

EDITABLE_STATUSES = (PeriodStatus.DRAFT, PeriodStatus.REOPENED)
ZERO = Decimal("0")


# --- Справочники и профили --------------------------------------------------------------


def list_time_codes() -> QuerySet[TimeCode]:
    return TimeCode.objects.all()


def list_worker_profiles() -> QuerySet[WorkerProfile]:
    return WorkerProfile.objects.select_related("employee", "employee__department")


def list_department_workers(department_id: UUID) -> list[WorkerProfile]:
    return list(
        WorkerProfile.objects.filter(employee__department_id=department_id)
        .select_related("employee", "employee__position")
        .order_by("employee__full_name")
    )


def get_worker_profile(employee_id: UUID) -> WorkerProfile | None:
    return (
        WorkerProfile.objects.filter(employee_id=employee_id)
        .select_related("employee", "employee__department", "employee__position")
        .first()
    )


def get_allocation(allocation_id: UUID) -> WorkAllocation | None:
    return (
        WorkAllocation.objects.filter(id=allocation_id)
        .select_related("employee", "time_code")
        .first()
    )


# --- Период -------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodState:
    """Состояние периода для экрана. Периода может ещё не быть: это черновик версии 1."""

    id: UUID | None
    department_id: UUID
    month: date
    status: PeriodStatus
    version: int

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES


def get_period(department_id: UUID, month: date) -> TimesheetPeriod | None:
    return TimesheetPeriod.objects.filter(department_id=department_id, month=month).first()


def period_state(department_id: UUID, month: date) -> PeriodState:
    period = get_period(department_id, month)
    if period is None:
        return PeriodState(None, department_id, month, PeriodStatus.DRAFT, 1)
    return PeriodState(period.id, department_id, month, PeriodStatus(period.status), period.version)


def is_period_editable(department_id: UUID, month: date) -> bool:
    return period_state(department_id, month_start(month)).is_editable


def list_period_events(period_id: UUID) -> list[TimesheetPeriodEvent]:
    return list(
        TimesheetPeriodEvent.objects.filter(period_id=period_id).select_related("actor", "manager")
    )


def confirmed_managers(events: Iterable[TimesheetPeriodEvent]) -> set[UUID]:
    """Менеджеры, подтвердившие часы после последней подачи: возврат и переоткрытие
    ведут к новой подаче, и прежние визы перестают действовать сами."""

    confirmed: set[UUID] = set()
    for event in events:
        if event.kind == PeriodEventKind.SUBMITTED:
            confirmed = set()
        elif event.kind == PeriodEventKind.MANAGER_CONFIRMED and event.manager_id is not None:
            confirmed.add(event.manager_id)
    return confirmed


def list_departments_with_workers() -> list[tuple[UUID, str, str, str]]:
    """(id, код, наименование, ФИО руководителя) подразделений, где ведётся табель."""

    rows = (
        WorkerProfile.objects.select_related("employee__department__head")
        .order_by("employee__department__name")
        .values_list(
            "employee__department_id",
            "employee__department__code",
            "employee__department__name",
            "employee__department__head__full_name",
        )
        .distinct()
    )
    return [(r[0], r[1], r[2], r[3] or "") for r in rows]


def period_statuses(month: date) -> dict[UUID, PeriodStatus]:
    return {
        department_id: PeriodStatus(status)
        for department_id, status in TimesheetPeriod.objects.filter(month=month).values_list(
            "department_id", "status"
        )
    }


# --- Разноска -------------------------------------------------------------------------


def list_month_allocations(employee_ids: Iterable[UUID], month: date) -> list[WorkAllocation]:
    days = month_days(month)
    return list(
        WorkAllocation.objects.filter(
            employee_id__in=list(employee_ids), date__gte=days[0], date__lte=days[-1]
        )
        .select_related("time_code")
        .order_by("employee_id", "date", "created_at")
    )


def list_day_allocations(employee_id: UUID, day: date) -> list[WorkAllocation]:
    return list(
        WorkAllocation.objects.filter(employee_id=employee_id, date=day)
        .select_related("time_code")
        .order_by("created_at", "id")
    )


def _fact(allocation: WorkAllocation) -> AllocationFact:
    return AllocationFact(
        employee_id=allocation.employee_id,
        date=allocation.date,
        code=allocation.time_code.code,
        is_work=allocation.time_code.is_work,
        target=allocation.target,
        hours=allocation.hours,
    )


def _check_worker(profile: WorkerProfile) -> CheckWorker:
    return CheckWorker(
        employee_id=profile.employee_id,
        full_name=profile.employee.full_name,
        has_work_center=profile.work_center_id is not None,
        active_from=profile.employee.hire_date,
        active_to=profile.employee.termination_date,
    )


def period_checks(department_id: UUID, month: date, today: date) -> list[Check]:
    workers = list_department_workers(department_id)
    allocations = list_month_allocations([w.employee_id for w in workers], month)
    return compute_checks(
        [_check_worker(w) for w in workers], [_fact(a) for a in allocations], month, today
    )


# --- Сетка месяца ------------------------------------------------------------------------


@dataclass(frozen=True)
class GridCell:
    date: date
    work_hours: Decimal  # рабочие часы без сверхурочных
    overtime_hours: Decimal
    absence_code: str
    is_trip: bool
    has_overhead: bool  # есть накладные или простой — подсветка «проверьте»
    is_missing: bool


@dataclass(frozen=True)
class ObjectLine:
    target: str
    order_id: UUID | None
    hours_by_day: dict[date, Decimal]
    total: Decimal


@dataclass(frozen=True)
class GridRow:
    employee_id: UUID
    full_name: str
    personnel_no: str
    position: str
    work_center_id: UUID | None
    cells: list[GridCell]
    objects: list[ObjectLine]
    total: Decimal
    norm: Decimal
    delta: Decimal


@dataclass(frozen=True)
class CodeTotal:
    code: str
    name: str
    hours: Decimal


@dataclass(frozen=True)
class ObjectTotal:
    target: str
    order_id: UUID | None
    analytics: str
    hours: Decimal


@dataclass(frozen=True)
class MonthGrid:
    period: PeriodState
    department_code: str
    department_name: str
    head_id: UUID | None
    head_name: str
    days: list[date]
    norm_hours: Decimal
    rows: list[GridRow]
    checks: list[Check]
    by_code: list[CodeTotal] = field(default_factory=list)
    by_object: list[ObjectTotal] = field(default_factory=list)


def _grid_row(
    profile: WorkerProfile, allocations: list[WorkAllocation], days: list[date], last: date | None
) -> GridRow:
    by_day: dict[date, list[WorkAllocation]] = defaultdict(list)
    objects: dict[tuple[str, UUID | None], dict[date, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for allocation in allocations:
        by_day[allocation.date].append(allocation)
        if allocation.target:
            objects[(allocation.target, allocation.order_id)][allocation.date] += allocation.hours

    cells: list[GridCell] = []
    total = absence_total = ZERO
    for day in days:
        rows = by_day.get(day, [])
        work = sum(
            (a.hours for a in rows if a.time_code.is_work and a.time_code.code != OVERTIME_CODE),
            ZERO,
        )
        overtime = sum((a.hours for a in rows if a.time_code.code == OVERTIME_CODE), ZERO)
        absence = next((a for a in rows if not a.time_code.is_work), None)
        total += work + overtime
        if absence is not None and last is not None and day <= last:
            absence_total += absence.hours
        cells.append(
            GridCell(
                date=day,
                work_hours=work,
                overtime_hours=overtime,
                absence_code=absence.time_code.code if absence is not None else "",
                is_trip=any(a.time_code.code == TRIP_CODE for a in rows),
                has_overhead=any(
                    a.target in (AllocationTarget.OVERHEAD, AllocationTarget.IDLE) for a in rows
                ),
                is_missing=not rows and not is_weekend(day) and last is not None and day <= last,
            )
        )

    month = days[0]
    norm = DAY_NORM * len(working_days_until(month, last)) - absence_total
    return GridRow(
        employee_id=profile.employee_id,
        full_name=profile.employee.full_name,
        personnel_no=profile.employee.personnel_number,
        position=profile.employee.position.name,
        work_center_id=profile.work_center_id,
        cells=cells,
        objects=[
            ObjectLine(target, order_id, dict(hours), sum(hours.values(), ZERO))
            for (target, order_id), hours in objects.items()
        ],
        total=total,
        norm=norm,
        delta=total - norm,
    )


def month_grid(
    department_id: UUID,
    month: date,
    today: date,
    order_numbers: Mapping[UUID, str] | None = None,
) -> MonthGrid | None:
    department = Department.objects.filter(id=department_id).select_related("head").first()
    if department is None:
        return None
    workers = list_department_workers(department_id)
    allocations = list_month_allocations([w.employee_id for w in workers], month)
    by_employee: dict[UUID, list[WorkAllocation]] = defaultdict(list)
    for allocation in allocations:
        by_employee[allocation.employee_id].append(allocation)

    days = month_days(month)
    last = last_closed_day(month, today)

    codes: dict[str, CodeTotal] = {}
    objects: dict[tuple[str, UUID | None], Decimal] = defaultdict(Decimal)
    for allocation in allocations:
        code = allocation.time_code
        current = codes.get(code.code)
        codes[code.code] = CodeTotal(
            code.code, code.name, (current.hours if current else ZERO) + allocation.hours
        )
        if allocation.target:
            objects[(allocation.target, allocation.order_id)] += allocation.hours

    numbers = order_numbers or {}
    return MonthGrid(
        period=period_state(department_id, month),
        department_code=department.code,
        department_name=department.name,
        head_id=department.head_id,
        head_name=department.head.full_name if department.head else "",
        days=days,
        norm_hours=DAY_NORM * len([d for d in days if not is_weekend(d)]),
        rows=[_grid_row(w, by_employee.get(w.employee_id, []), days, last) for w in workers],
        checks=compute_checks(
            [_check_worker(w) for w in workers], [_fact(a) for a in allocations], month, today
        ),
        by_code=sorted(codes.values(), key=lambda c: c.code),
        by_object=sorted(
            (
                ObjectTotal(
                    target,
                    order_id,
                    analytics_for(target, order_id, department.code, numbers),
                    hours,
                )
                for (target, order_id), hours in objects.items()
            ),
            key=lambda o: -o.hours,
        ),
    )


# --- Часы по заказам менеджеров (`mgrHours`) ---------------------------------------------


def department_order_hours(department_id: UUID, month: date) -> dict[UUID, Decimal]:
    """Заказ → часы работников подразделения за месяц."""

    workers = list_department_workers(department_id)
    days = month_days(month)
    hours: dict[UUID, Decimal] = defaultdict(Decimal)
    rows = WorkAllocation.objects.filter(
        employee_id__in=[w.employee_id for w in workers],
        date__gte=days[0],
        date__lte=days[-1],
        target=AllocationTarget.ORDER,
    ).values_list("order_id", "hours")
    for order_id, value in rows:
        if order_id is not None:
            hours[order_id] += value
    return dict(hours)


def manager_hours(
    order_hours: Mapping[UUID, Decimal], order_managers: Mapping[UUID, UUID]
) -> dict[UUID, dict[UUID, Decimal]]:
    """Менеджер → {заказ: часы}. Заказ без менеджера визы не требует."""

    result: dict[UUID, dict[UUID, Decimal]] = defaultdict(dict)
    for order_id, value in order_hours.items():
        manager_id = order_managers.get(order_id)
        if manager_id is not None:
            result[manager_id][order_id] = value
    return dict(result)


# --- Пакеты 1С ------------------------------------------------------------------------


def period_packages(
    department_id: UUID, month: date, order_numbers: Mapping[UUID, str]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    department = Department.objects.filter(id=department_id).select_related("head").first()
    if department is None:
        return None
    state = period_state(department_id, month)
    workers = list_department_workers(department_id)
    numbers = {w.employee_id: w.employee.personnel_number for w in workers}
    facts = [
        PackageFact(
            personnel_no=numbers[a.employee_id],
            date=a.date,
            code=a.time_code.code,
            is_work=a.time_code.is_work,
            target=a.target,
            order_id=a.order_id,
            hours=a.hours,
        )
        for a in list_month_allocations(numbers.keys(), month)
    ]
    return build_packages(
        facts,
        month=month,
        department_code=department.code,
        version=state.version,
        order_numbers=order_numbers,
    )


# --- Для фасада -----------------------------------------------------------------------


@dataclass(frozen=True)
class AllocationRow:
    employee_id: UUID
    date: date
    code: str
    is_work: bool
    cost_multiplier: Decimal
    target: str
    order_id: UUID | None
    operation_id: UUID | None
    hours: Decimal
    work_center_id: UUID | None
    hourly_rate: Decimal


def _profiles_by_employee(employee_ids: Iterable[UUID]) -> dict[UUID, WorkerProfile]:
    return {
        p.employee_id: p
        for p in WorkerProfile.objects.filter(employee_id__in=list(set(employee_ids)))
    }


def list_allocation_rows(date_from: date, date_to: date) -> list[AllocationRow]:
    allocations = list(
        WorkAllocation.objects.filter(date__gte=date_from, date__lte=date_to)
        .select_related("time_code")
        .order_by("date", "employee_id", "created_at")
    )
    profiles = _profiles_by_employee(a.employee_id for a in allocations)
    rows = []
    for a in allocations:
        profile = profiles.get(a.employee_id)
        rows.append(
            AllocationRow(
                employee_id=a.employee_id,
                date=a.date,
                code=a.time_code.code,
                is_work=a.time_code.is_work,
                cost_multiplier=a.time_code.cost_multiplier,
                target=a.target,
                order_id=a.order_id,
                operation_id=a.operation_id,
                hours=a.hours,
                work_center_id=profile.work_center_id if profile else None,
                hourly_rate=profile.hourly_rate if profile else ZERO,
            )
        )
    return rows


def worked_hours_by_work_center(date_from: date, date_to: date) -> dict[UUID, Decimal]:
    """Отработанные часы (рабочие коды) по участку работника — знаменатель выработки."""

    result: dict[UUID, Decimal] = defaultdict(Decimal)
    rows = WorkAllocation.objects.filter(
        date__gte=date_from,
        date__lte=date_to,
        time_code__is_work=True,
        employee__worker_profile__work_center_id__isnull=False,
    ).values_list("employee__worker_profile__work_center_id", "hours")
    for work_center_id, hours in rows:
        if work_center_id is not None:
            result[work_center_id] += hours
    return dict(result)


@dataclass(frozen=True)
class OrderActual:
    hours: Decimal
    cost: Decimal


def actual_by_order(order_ids: Iterable[UUID]) -> dict[UUID, OrderActual]:
    """Фактические трудозатраты заказа (`tsActual`): часы и стоимость = часы × ставка
    работника × коэффициент кода. Без профиля ставка 0 — стоимость не выдумывается."""

    allocations = list(
        WorkAllocation.objects.filter(order_id__in=list(order_ids)).select_related("time_code")
    )
    profiles = _profiles_by_employee(a.employee_id for a in allocations)
    hours: dict[UUID, Decimal] = defaultdict(Decimal)
    cost: dict[UUID, Decimal] = defaultdict(Decimal)
    for a in allocations:
        if a.order_id is None:
            continue
        profile = profiles.get(a.employee_id)
        rate = profile.hourly_rate if profile else ZERO
        hours[a.order_id] += a.hours
        cost[a.order_id] += a.hours * rate * a.time_code.cost_multiplier
    return {order_id: OrderActual(hours[order_id], cost[order_id]) for order_id in hours}


def hourly_rates(employee_ids: Iterable[UUID]) -> dict[UUID, Decimal]:
    return dict(
        WorkerProfile.objects.filter(employee_id__in=list(employee_ids)).values_list(
            "employee_id", "hourly_rate"
        )
    )
