"""Эндпоинты django-ninja модуля «Табель» — экран «Табель» (спецификация §3.5, §6).

Права проверяются здесь, сервисы их не проверяют (как в ИС). Сетка и согласование
отдают серверные `abilities` — фронт показывает действия по ним. Данные о заказах
(менеджеры, номера, план участка) — через `production_link`, до слияния с
`production` пустые.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone
from ninja import Router
from ninja.responses import Status

from src.core.common.exceptions import PermissionDenied
from src.core.org import facade as org
from src.timesheet import production_link, selectors
from src.timesheet.calculations import (
    PlannedOp,
    is_weekend,
    last_closed_day,
    working_days_until,
)
from src.timesheet.exceptions import InvalidMonth
from src.timesheet.models import (
    AllocationSource,
    PackageType,
    PeriodEventKind,
    PeriodStatus,
    WorkAllocation,
)
from src.timesheet.rules import (
    can_approve_period,
    can_edit_department,
    current_employee_id,
)
from src.timesheet.services import allocation as allocation_services
from src.timesheet.services import period as period_services

from .schemas import (
    AllocationIn,
    AllocationOut,
    AllocationRowIn,
    CheckOut,
    CodeTotalOut,
    DayHoursOut,
    DayIn,
    DayOut,
    DepartmentPeriodOut,
    FillResultOut,
    GridCellOut,
    GridDayOut,
    GridRowOut,
    ManagerOrderHoursOut,
    ManagerVisaOut,
    MonthGridOut,
    ObjectLineOut,
    ObjectTotalOut,
    PeriodAbilitiesOut,
    PeriodEventOut,
    PeriodOut,
    PeriodReviewOut,
    PlannedOpOut,
    ReasonIn,
    TimeCodeOut,
)

router = Router(tags=["timesheet"])

PERIOD = "/departments/{department_id}/periods/{month}"


class _AuthenticatedUser(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


class AuthenticatedHttpRequest(HttpRequest):
    auth: _AuthenticatedUser


def _month(month: date) -> date:
    if month.day != 1:
        raise InvalidMonth
    return month


# --- Права и способности ---------------------------------------------------------------


def _require_edit(user: _AuthenticatedUser, department_id: UUID | None) -> None:
    if not can_edit_department(user, department_id):
        raise PermissionDenied(
            "Разноску подразделения правят его руководитель, мастер участка или "
            "начальник производства."
        )


def _require_approve(user: _AuthenticatedUser) -> None:
    if not can_approve_period(user):
        raise PermissionDenied("Согласует табель и передаёт его в 1С экономист.")


def _department_of(employee_id: UUID) -> UUID:
    department_id = org.get_department_id_for_employee(employee_id)
    if department_id is None:
        raise Http404
    return department_id


def _managers_state(
    department_id: UUID, month: date, period_id: UUID | None
) -> tuple[dict[UUID, dict[UUID, Decimal]], set[UUID]]:
    order_hours = selectors.department_order_hours(department_id, month)
    managers = selectors.manager_hours(order_hours, production_link.order_managers(order_hours))
    confirmed = (
        selectors.confirmed_managers(selectors.list_period_events(period_id))
        if period_id is not None
        else set()
    )
    return managers, confirmed


def _period_out(
    user: _AuthenticatedUser,
    department_id: UUID,
    month: date,
    has_blocking: bool | None = None,
) -> PeriodOut:
    state = selectors.period_state(department_id, month)
    if has_blocking is None:
        has_blocking = any(
            c.is_blocking
            for c in selectors.period_checks(department_id, month, timezone.localdate())
        )
    editor = bool(can_edit_department(user, department_id))
    approver = bool(can_approve_period(user))
    on_review = state.status == PeriodStatus.ON_REVIEW
    managers, confirmed = (
        _managers_state(department_id, month, state.id) if on_review else ({}, set())
    )
    me = current_employee_id(user) if on_review else None
    return PeriodOut(
        department_id=department_id,
        month=month,
        status=state.status,
        version=state.version,
        abilities=PeriodAbilitiesOut(
            can_edit=state.is_editable and editor,
            can_fill_plan=state.is_editable and editor,
            can_submit=state.is_editable and editor and not has_blocking,
            can_confirm_manager=me is not None and me in managers and me not in confirmed,
            can_approve=on_review and approver and set(managers) <= confirmed,
            can_return=on_review and approver,
            can_send=state.status == PeriodStatus.APPROVED and approver,
            can_close=state.status == PeriodStatus.SENT and approver,
            can_reopen=state.status in (PeriodStatus.SENT, PeriodStatus.CLOSED) and approver,
        ),
    )


# --- Справочники -------------------------------------------------------------------------


@router.get("/time-codes", response=list[TimeCodeOut], operation_id="listTimeCodes")
def list_time_codes(request: HttpRequest) -> list[TimeCodeOut]:
    return [
        TimeCodeOut(
            id=c.id,
            code=c.code,
            name=c.name,
            is_work=c.is_work,
            is_allocatable=c.is_allocatable,
            cost_multiplier=c.cost_multiplier,
        )
        for c in selectors.list_time_codes()
    ]


@router.get(
    "/departments", response=list[DepartmentPeriodOut], operation_id="listTimesheetDepartments"
)
def list_departments(request: HttpRequest, month: date) -> list[DepartmentPeriodOut]:
    """Подразделения с работниками и статус их табеля за месяц — выбор на экране."""

    statuses = selectors.period_statuses(_month(month))
    return [
        DepartmentPeriodOut(
            department_id=department_id,
            code=code,
            name=name,
            head_name=head_name,
            status=statuses.get(department_id, PeriodStatus.DRAFT),
        )
        for department_id, code, name, head_name in selectors.list_departments_with_workers()
    ]


# --- Сетка и согласование ---------------------------------------------------------------


@router.get(f"{PERIOD}/grid", response=MonthGridOut, operation_id="getTimesheetGrid")
def get_grid(request: AuthenticatedHttpRequest, department_id: UUID, month: date) -> MonthGridOut:
    month = _month(month)
    grid = selectors.month_grid(department_id, month, timezone.localdate())
    if grid is None:
        raise Http404
    return MonthGridOut(
        period=_period_out(
            request.auth, department_id, month, any(c.is_blocking for c in grid.checks)
        ),
        department_code=grid.department_code,
        department_name=grid.department_name,
        head_id=grid.head_id,
        head_name=grid.head_name,
        days=[GridDayOut(date=d, is_weekend=is_weekend(d)) for d in grid.days],
        norm_hours=grid.norm_hours,
        rows=[
            GridRowOut(
                employee_id=row.employee_id,
                full_name=row.full_name,
                personnel_no=row.personnel_no,
                position=row.position,
                work_center_id=row.work_center_id,
                cells=[
                    GridCellOut(
                        date=c.date,
                        work_hours=c.work_hours,
                        overtime_hours=c.overtime_hours,
                        absence_code=c.absence_code,
                        is_trip=c.is_trip,
                        has_overhead=c.has_overhead,
                        is_missing=c.is_missing,
                    )
                    for c in row.cells
                ],
                objects=[
                    ObjectLineOut(
                        target=o.target,
                        order_id=o.order_id,
                        days=[
                            DayHoursOut(date=d, hours=h) for d, h in sorted(o.hours_by_day.items())
                        ],
                        total=o.total,
                    )
                    for o in row.objects
                ],
                total=row.total,
                norm=row.norm,
                delta=row.delta,
            )
            for row in grid.rows
        ],
        checks=[
            CheckOut(is_blocking=c.is_blocking, text=c.text, employee_id=c.employee_id)
            for c in grid.checks
        ],
        by_code=[CodeTotalOut(code=c.code, name=c.name, hours=c.hours) for c in grid.by_code],
        by_object=[
            ObjectTotalOut(
                target=o.target, order_id=o.order_id, analytics=o.analytics, hours=o.hours
            )
            for o in grid.by_object
        ],
    )


@router.get(f"{PERIOD}/review", response=PeriodReviewOut, operation_id="getTimesheetReview")
def get_review(
    request: AuthenticatedHttpRequest, department_id: UUID, month: date
) -> PeriodReviewOut:
    """Визы менеджеров по своим заказам (`mgrHours`) и журнал переходов периода."""

    month = _month(month)
    state = selectors.period_state(department_id, month)
    managers, confirmed = _managers_state(department_id, month, state.id)
    names = {b.id: b.full_name for b in org.list_active_employees()} if managers else {}
    me = current_employee_id(request.auth)
    events = selectors.list_period_events(state.id) if state.id is not None else []
    return PeriodReviewOut(
        period=_period_out(request.auth, department_id, month),
        managers=[
            ManagerVisaOut(
                manager_id=manager_id,
                manager_name=names.get(manager_id, ""),
                orders=[
                    ManagerOrderHoursOut(order_id=order_id, hours=hours)
                    for order_id, hours in orders.items()
                ],
                confirmed=manager_id in confirmed,
                can_confirm=state.status == PeriodStatus.ON_REVIEW
                and me == manager_id
                and manager_id not in confirmed,
            )
            for manager_id, orders in managers.items()
        ],
        events=[
            PeriodEventOut(
                kind=PeriodEventKind(e.kind),
                version=e.version,
                actor_name=e.actor.display_name if e.actor else "",
                manager_name=e.manager.full_name if e.manager else "",
                comment=e.comment,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


def _day_plans(department_id: UUID, month: date) -> list[allocation_services.DayPlan]:
    last = last_closed_day(month, timezone.localdate())
    days = working_days_until(month, last)
    return [
        allocation_services.DayPlan(
            employee_id=worker.employee_id,
            day=day,
            planned=production_link.planned_operations(worker.work_center_id, day),
        )
        for worker in selectors.list_department_workers(department_id)
        for day in days
    ]


@router.post(
    f"{PERIOD}/fill-from-plan", response=FillResultOut, operation_id="fillTimesheetFromPlan"
)
def fill_from_plan(
    request: AuthenticatedHttpRequest, department_id: UUID, month: date
) -> FillResultOut:
    """Незакрытые будние дни до вчера — по плану операций участков."""

    month = _month(month)
    _require_edit(request.auth, department_id)
    filled = allocation_services.fill_days_from_plan(
        _day_plans(department_id, month), actor_id=request.auth.id
    )
    return FillResultOut(filled_days=filled, period=_period_out(request.auth, department_id, month))


@router.post(f"{PERIOD}/submit", response=PeriodOut, operation_id="submitTimesheet")
def submit(request: AuthenticatedHttpRequest, department_id: UUID, month: date) -> PeriodOut:
    month = _month(month)
    _require_edit(request.auth, department_id)
    period_services.submit_period(
        department_id, month, today=timezone.localdate(), actor_id=request.auth.id
    )
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/confirm-manager", response=PeriodOut, operation_id="confirmTimesheetHours")
def confirm_manager(
    request: AuthenticatedHttpRequest, department_id: UUID, month: date
) -> PeriodOut:
    """Виза менеджера по часам на свои заказы — ставит сам менеджер."""

    month = _month(month)
    me = current_employee_id(request.auth)
    if me is None:
        raise PermissionDenied("Подтверждает часы менеджер заказа — пользователь без сотрудника.")
    order_hours = selectors.department_order_hours(department_id, month)
    period_services.confirm_manager_hours(
        department_id,
        month,
        me,
        order_managers=production_link.order_managers(order_hours),
        actor_id=request.auth.id,
    )
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/approve", response=PeriodOut, operation_id="approveTimesheet")
def approve(request: AuthenticatedHttpRequest, department_id: UUID, month: date) -> PeriodOut:
    month = _month(month)
    _require_approve(request.auth)
    order_hours = selectors.department_order_hours(department_id, month)
    period_services.approve_period(
        department_id,
        month,
        order_managers=production_link.order_managers(order_hours),
        actor_id=request.auth.id,
    )
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/return", response=PeriodOut, operation_id="returnTimesheet")
def return_view(
    request: AuthenticatedHttpRequest, department_id: UUID, month: date, data: ReasonIn
) -> PeriodOut:
    month = _month(month)
    _require_approve(request.auth)
    period_services.return_period(department_id, month, data.comment, actor_id=request.auth.id)
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/send", response=PeriodOut, operation_id="sendTimesheet")
def send(request: AuthenticatedHttpRequest, department_id: UUID, month: date) -> PeriodOut:
    """Передача в 1С: статус `sent`; сами пакеты скачиваются `.../packages/{тип}`."""

    month = _month(month)
    _require_approve(request.auth)
    order_ids = selectors.department_order_hours(department_id, month)
    period_services.send_period(
        department_id,
        month,
        order_numbers=production_link.order_numbers(order_ids),
        actor_id=request.auth.id,
    )
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/close", response=PeriodOut, operation_id="closeTimesheet")
def close(request: AuthenticatedHttpRequest, department_id: UUID, month: date) -> PeriodOut:
    month = _month(month)
    _require_approve(request.auth)
    period_services.close_period(department_id, month, actor_id=request.auth.id)
    return _period_out(request.auth, department_id, month)


@router.post(f"{PERIOD}/reopen", response=PeriodOut, operation_id="reopenTimesheet")
def reopen(
    request: AuthenticatedHttpRequest, department_id: UUID, month: date, data: ReasonIn
) -> PeriodOut:
    month = _month(month)
    _require_approve(request.auth)
    period_services.reopen_period(department_id, month, data.comment, actor_id=request.auth.id)
    return _period_out(request.auth, department_id, month)


@router.get(f"{PERIOD}/packages/{{package_type}}", operation_id="downloadTimesheetPackage")
def download_package(
    request: HttpRequest, department_id: UUID, month: date, package_type: PackageType
) -> HttpResponse:
    """Пакет обмена с 1С файлом JSON (ИС ADR 0002: транспорт в 1С вне объёма)."""

    month = _month(month)
    order_ids = selectors.department_order_hours(department_id, month)
    packages = selectors.period_packages(
        department_id, month, production_link.order_numbers(order_ids)
    )
    if packages is None:
        raise Http404
    timesheet, cost_allocation = packages
    payload = timesheet if package_type == PackageType.TIMESHEET else cost_allocation
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    filename = f"{package_type.value}_{month:%Y-%m}_v{payload['version']}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --- Разноска дня ----------------------------------------------------------------------


def _allocation_out(a: WorkAllocation) -> AllocationOut:
    return AllocationOut(
        id=a.id,
        employee_id=a.employee_id,
        date=a.date,
        time_code=a.time_code.code,
        time_code_name=a.time_code.name,
        is_work=a.time_code.is_work,
        target=a.target,
        order_id=a.order_id,
        operation_id=a.operation_id,
        hours=a.hours,
        source=AllocationSource(a.source),
        source_ref=a.source_ref,
    )


def _row_dto(row: AllocationRowIn) -> allocation_services.AllocationDTO:
    return allocation_services.AllocationDTO(
        time_code=row.time_code,
        hours=row.hours,
        target=row.target,
        order_id=row.order_id,
        operation_id=row.operation_id,
    )


def _plan_out(op: PlannedOp) -> PlannedOpOut:
    return PlannedOpOut(operation_id=op.operation_id, order_id=op.order_id, label=op.label)


def _day_out(user: _AuthenticatedUser, employee_id: UUID, day: date) -> DayOut:
    profile = selectors.get_worker_profile(employee_id)
    if profile is None:
        raise Http404
    employee = profile.employee
    rows = selectors.list_day_allocations(employee_id, day)
    editable = selectors.is_period_editable(employee.department_id, day)
    return DayOut(
        employee_id=employee_id,
        full_name=employee.full_name,
        position=employee.position.name,
        department_id=employee.department_id,
        department_name=employee.department.name,
        work_center_id=profile.work_center_id,
        date=day,
        rows=[_allocation_out(a) for a in rows],
        total=sum((a.hours for a in rows), Decimal("0")),
        can_edit=editable and bool(can_edit_department(user, employee.department_id)),
        planned=[
            _plan_out(op) for op in production_link.planned_operations(profile.work_center_id, day)
        ],
    )


@router.get("/employees/{employee_id}/days/{day}", response=DayOut, operation_id="getTimesheetDay")
def get_day(request: AuthenticatedHttpRequest, employee_id: UUID, day: date) -> DayOut:
    return _day_out(request.auth, employee_id, day)


@router.put("/employees/{employee_id}/days/{day}", response=DayOut, operation_id="saveTimesheetDay")
def save_day(
    request: AuthenticatedHttpRequest, employee_id: UUID, day: date, data: DayIn
) -> DayOut:
    """Сохранение диалога дня: строки дня заменяются целиком."""

    _require_edit(request.auth, _department_of(employee_id))
    allocation_services.replace_day(
        employee_id, day, [_row_dto(r) for r in data.rows], actor_id=request.auth.id
    )
    return _day_out(request.auth, employee_id, day)


@router.post(
    "/employees/{employee_id}/days/{day}/fill-from-plan",
    response=DayOut,
    operation_id="fillTimesheetDayFromPlan",
)
def fill_day(request: AuthenticatedHttpRequest, employee_id: UUID, day: date) -> DayOut:
    _require_edit(request.auth, _department_of(employee_id))
    profile = selectors.get_worker_profile(employee_id)
    if profile is None:
        raise Http404
    allocation_services.fill_day_from_plan(
        employee_id,
        day,
        production_link.planned_operations(profile.work_center_id, day),
        actor_id=request.auth.id,
    )
    return _day_out(request.auth, employee_id, day)


@router.post("/allocations", response=AllocationOut, operation_id="createAllocation")
def create_allocation(request: AuthenticatedHttpRequest, data: AllocationIn) -> AllocationOut:
    _require_edit(request.auth, _department_of(data.employee_id))
    created = allocation_services.create_allocation(
        data.employee_id, data.date, _row_dto(data), actor_id=request.auth.id
    )
    found = selectors.get_allocation(created.id)
    if found is None:
        raise Http404
    return _allocation_out(found)


def _allocation_or_404(allocation_id: UUID) -> WorkAllocation:
    found = selectors.get_allocation(allocation_id)
    if found is None:
        raise Http404
    return found


@router.patch(
    "/allocations/{allocation_id}", response=AllocationOut, operation_id="updateAllocation"
)
def update_allocation(
    request: AuthenticatedHttpRequest, allocation_id: UUID, data: AllocationRowIn
) -> AllocationOut:
    found = _allocation_or_404(allocation_id)
    _require_edit(request.auth, found.employee.department_id)
    allocation_services.update_allocation(allocation_id, _row_dto(data), actor_id=request.auth.id)
    return _allocation_out(_allocation_or_404(allocation_id))


@router.delete(
    "/allocations/{allocation_id}", response={204: None}, operation_id="deleteAllocation"
)
def delete_allocation(request: AuthenticatedHttpRequest, allocation_id: UUID) -> Status[None]:
    found = _allocation_or_404(allocation_id)
    _require_edit(request.auth, found.employee.department_id)
    allocation_services.delete_allocation(allocation_id, actor_id=request.auth.id)
    return Status(204, None)
