"""Разноска — первичный ввод табеля (И7): строки дня, «заполнить по плану».
Единственное место транзакций для `WorkAllocation` (И3).

Правка — только в открытом периоде подразделения сотрудника (`draft`/`reopened`).
Период блокируется `select_for_update` — точка сериализации правок одного табеля:
две параллельные правки дня не обойдут вдвоём проверку «≤ 24 ч в сумме».
Права проверяются в API и админке (как в ИС): сервис зовёт и обработчик события.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.core.org.models import Employee
from src.timesheet.calculations import (
    DAY_LIMIT,
    PRESENCE_CODE,
    PlannedOp,
    is_weekend,
    month_start,
    split_plan_hours,
)
from src.timesheet.exceptions import (
    DayLimitExceeded,
    EmployeeNotFound,
    InvalidAllocation,
    NotAWorker,
    PeriodLocked,
    TimeCodeNotFound,
)
from src.timesheet.models import (
    AllocationSource,
    AllocationTarget,
    TimeCode,
    WorkAllocation,
    WorkerProfile,
)
from src.timesheet.services.period import EDITABLE_STATUSES, lock_period


@dataclass(frozen=True)
class AllocationDTO:
    time_code: str
    hours: Decimal
    target: str = ""
    order_id: UUID | None = None
    operation_id: UUID | None = None


@dataclass(frozen=True)
class DayPlan:
    employee_id: UUID
    day: date
    planned: Sequence[PlannedOp]


def lock_open_period_for(employee_id: UUID, day: date) -> Employee:
    """Сотрудник и открытый период его подразделения за месяц дня — под блокировкой."""

    employee = Employee.objects.filter(id=employee_id).first()
    if employee is None:
        raise EmployeeNotFound
    period = lock_period(employee.department_id, month_start(day))
    if period.status not in EDITABLE_STATUSES:
        raise PeriodLocked
    return employee


def _require_worker(employee_id: UUID) -> None:
    if not WorkerProfile.objects.filter(employee_id=employee_id).exists():
        raise NotAWorker


def _time_code(code: str) -> TimeCode:
    found = TimeCode.objects.filter(code=code).first()
    if found is None:
        raise TimeCodeNotFound
    return found


def _validated(data: AllocationDTO) -> tuple[TimeCode, AllocationDTO]:
    """Код определяет, есть ли у строки объект: разносимое время — на заказ, накладные,
    ремонт, обучение или простой; отпуск и больничный — без объекта."""

    code = _time_code(data.time_code)
    if not (Decimal("0") < data.hours <= DAY_LIMIT):
        raise InvalidAllocation("Часы строки — больше нуля и не больше 24.")
    if not code.is_allocatable:
        if data.target or data.order_id or data.operation_id:
            raise InvalidAllocation(f"Код «{code.code}» не разносится на объекты.")
        return code, data
    if data.target not in AllocationTarget.values:
        raise InvalidAllocation("Укажите, на что разнесены часы.")
    if data.target == AllocationTarget.ORDER and data.order_id is None:
        raise InvalidAllocation("Укажите заказ.")
    if data.target != AllocationTarget.ORDER and (data.order_id or data.operation_id):
        raise InvalidAllocation("Заказ и операция указываются только у строки на заказ.")
    return code, data


def _check_day_limit(employee_id: UUID, day: date, *, exclude_id: UUID | None = None) -> None:
    rows = WorkAllocation.objects.filter(employee_id=employee_id, date=day)
    if exclude_id is not None:
        rows = rows.exclude(id=exclude_id)
    total = sum(rows.values_list("hours", flat=True), Decimal("0"))
    if total > DAY_LIMIT:
        raise DayLimitExceeded


def _build(
    employee_id: UUID,
    day: date,
    code: TimeCode,
    data: AllocationDTO,
    source: AllocationSource,
    source_ref: str = "",
) -> WorkAllocation:
    return WorkAllocation(
        employee_id=employee_id,
        date=day,
        time_code=code,
        target=data.target,
        order_id=data.order_id,
        operation_id=data.operation_id,
        hours=data.hours,
        source=source,
        source_ref=source_ref,
    )


def create_allocation(
    employee_id: UUID, day: date, data: AllocationDTO, *, actor_id: UUID
) -> WorkAllocation:
    _require_worker(employee_id)
    code, data = _validated(data)
    with transaction.atomic(), actor_context(actor_id):
        lock_open_period_for(employee_id, day)
        allocation = _build(employee_id, day, code, data, AllocationSource.MANUAL)
        allocation.save()
        _check_day_limit(employee_id, day)
        return allocation


def update_allocation(allocation_id: UUID, data: AllocationDTO, *, actor_id: UUID) -> None:
    """Ручная правка делает строку ручной: источник «план» или «ремонт» больше не
    описывает её часы."""

    code, data = _validated(data)
    with transaction.atomic(), actor_context(actor_id):
        allocation = WorkAllocation.objects.select_for_update().get(id=allocation_id)
        lock_open_period_for(allocation.employee_id, allocation.date)
        allocation.time_code = code
        allocation.target = data.target
        allocation.order_id = data.order_id
        allocation.operation_id = data.operation_id
        allocation.hours = data.hours
        allocation.source = AllocationSource.MANUAL
        allocation.source_ref = ""
        allocation.save()
        _check_day_limit(allocation.employee_id, allocation.date)


def delete_allocation(allocation_id: UUID, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        allocation = WorkAllocation.objects.select_for_update().get(id=allocation_id)
        lock_open_period_for(allocation.employee_id, allocation.date)
        allocation.delete()


def replace_day(
    employee_id: UUID, day: date, rows: Sequence[AllocationDTO], *, actor_id: UUID
) -> list[WorkAllocation]:
    """Сохранение диалога дня (`dayDialog` прототипа): строки дня заменяются целиком.
    Пустой список — день очищен."""

    _require_worker(employee_id)
    validated = [_validated(row) for row in rows]
    if sum((data.hours for _, data in validated), Decimal("0")) > DAY_LIMIT:
        raise DayLimitExceeded
    with transaction.atomic(), actor_context(actor_id):
        lock_open_period_for(employee_id, day)
        WorkAllocation.objects.filter(employee_id=employee_id, date=day).delete()
        return WorkAllocation.objects.bulk_create(
            [
                _build(employee_id, day, code, data, AllocationSource.MANUAL)
                for code, data in validated
            ]
        )


def _plan_rows(employee_id: UUID, day: date, planned: Sequence[PlannedOp]) -> list[WorkAllocation]:
    code = _time_code(PRESENCE_CODE)
    shares, rest = split_plan_hours(len(planned))
    rows = [
        _build(
            employee_id,
            day,
            code,
            AllocationDTO(
                time_code=code.code,
                hours=hours,
                target=AllocationTarget.ORDER,
                order_id=op.order_id,
                operation_id=op.operation_id,
            ),
            AllocationSource.PLAN,
        )
        for op, hours in zip(planned, shares, strict=True)
    ]
    if rest > 0:
        rows.append(
            _build(
                employee_id,
                day,
                code,
                AllocationDTO(time_code=code.code, hours=rest, target=AllocationTarget.OVERHEAD),
                AllocationSource.PLAN,
            )
        )
    return rows


def _fill_one(employee_id: UUID, day: date, planned: Sequence[PlannedOp]) -> int:
    if is_weekend(day) or WorkAllocation.objects.filter(employee_id=employee_id, date=day).exists():
        return 0
    WorkAllocation.objects.bulk_create(_plan_rows(employee_id, day, planned))
    return 1


def fill_day_from_plan(
    employee_id: UUID, day: date, planned: Sequence[PlannedOp], *, actor_id: UUID
) -> int:
    """«Заполнить по плану» (`autoFillDay`): только незакрытый будний день. 8 ч
    поровну на плановые операции участка, остаток — накладные; без плана — 8 ч
    накладных. Возвращает число заполненных дней (0 или 1).

    Плановые операции — аргумент: их даёт `production.facade.list_planned_operations`
    через `production_link`, сам табель о графике заказов не знает."""

    _require_worker(employee_id)
    with transaction.atomic(), actor_context(actor_id):
        lock_open_period_for(employee_id, day)
        return _fill_one(employee_id, day, planned)


def fill_days_from_plan(items: Sequence[DayPlan], *, actor_id: UUID) -> int:
    """Кнопка «Заполнить по плану» для всего табеля — одной транзакцией."""

    filled = 0
    with transaction.atomic(), actor_context(actor_id):
        for item in items:
            _require_worker(item.employee_id)
            lock_open_period_for(item.employee_id, item.day)
            filled += _fill_one(item.employee_id, item.day, item.planned)
    return filled
