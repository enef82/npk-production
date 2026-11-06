"""Чистые расчёты аналитики (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8): недели и
месяцы, распределение часов по рабочим дням, показатели отсечки, выработка сотрудников.

Без обращений к БД (CLAUDE.md §5): селекторы собирают данные фасадов, здесь только
арифметика — её и проверяют тесты точными `Decimal`. Округление — только на выводе:
промежуточные доли хранятся полной точностью контекста `Decimal`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from src.core.common.scheduling import add_working_days, working_days_between
from src.timesheet.facade import AllocationTarget

ZERO = Decimal("0")
HUNDRED = Decimal("100")
HOURS_PER_DAY = Decimal("8")
HOURS_PER_WEEK = Decimal("40")
_CENTS = Decimal("0.01")
_TENTHS = Decimal("0.1")


# --- Календарь -----------------------------------------------------------------------


def week_start(day: date) -> date:
    """Понедельник недели (`wkOf` прототипа)."""

    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(month: date, n: int) -> date:
    total = month.year * 12 + month.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def month_end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def working_days_in_month(month: date) -> int:
    """Рабочие дни (пн–пт) месяца — праздников нет (§2.1)."""

    day, count = month_start(month), 0
    while day.month == month.month:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def operation_days(start: date, finish: date) -> list[date]:
    """Рабочие дни операции от начала до окончания включительно (`opDays`)."""

    return [add_working_days(start, k) for k in range(working_days_between(start, finish) + 1)]


# --- Округление и доли -----------------------------------------------------------------


def hours2(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, ROUND_HALF_UP)


def pct(part: Decimal, whole: Decimal) -> Decimal | None:
    """Доля в процентах с одним знаком; без базы — `None` («—» на экране)."""

    if not whole:
        return None
    return (part * HUNDRED / whole).quantize(_TENTHS, ROUND_HALF_UP)


def ratio(part: Decimal, whole: Decimal) -> Decimal | None:
    """Отношение с двумя знаками (отдача, ₽ на ₽)."""

    if not whole:
        return None
    return (part / whole).quantize(_CENTS, ROUND_HALF_UP)


# --- Распределение часов по дням -------------------------------------------------------


@dataclass(frozen=True)
class SpreadOp:
    """Операция для распределения часов: участок, часы к распределению, дни операции."""

    work_center_id: UUID
    hours: Decimal
    start: date
    finish: date


def spread_by_week(ops: Iterable[SpreadOp]) -> dict[tuple[date, UUID], Decimal]:
    """Часы операций поровну на каждый рабочий день операции, свёрнутые по (неделя,
    участок) — `planByWeek` и сетка `renderLoad` прототипа."""

    result: dict[tuple[date, UUID], Decimal] = defaultdict(Decimal)
    for op in ops:
        days = operation_days(op.start, op.finish)
        per_day = op.hours / Decimal(len(days))
        for day in days:
            result[(week_start(day), op.work_center_id)] += per_day
    return dict(result)


def spread_by_month(
    ops: Iterable[SpreadOp], *, not_before: date
) -> dict[tuple[date, UUID], Decimal]:
    """Остаток часов на оставшиеся рабочие дни операции (не раньше `not_before`), по
    (месяц, участок) — загрузка портфеля. Операция, чьи дни уже прошли, ложится на
    `not_before` целиком: часы не выполнены и всё ещё займут мощность (`portfolioData`)."""

    result: dict[tuple[date, UUID], Decimal] = defaultdict(Decimal)
    for op in ops:
        days = [d for d in operation_days(op.start, op.finish) if d >= not_before] or [not_before]
        per_day = op.hours / Decimal(len(days))
        for day in days:
            result[(month_start(day), op.work_center_id)] += per_day
    return dict(result)


def remaining_hours(hours: Decimal, progress: int | Decimal) -> Decimal:
    """Невыполненный остаток `hours × (1 − прогресс/100)`."""

    return hours * (HUNDRED - Decimal(progress)) / HUNDRED


# --- Выработка сотрудников (`empStats`) ------------------------------------------------


@dataclass(frozen=True)
class Allocation:
    employee_id: UUID
    date: date
    is_work: bool
    cost_multiplier: Decimal
    target: str
    operation_id: UUID | None
    hours: Decimal
    hourly_rate: Decimal


@dataclass(frozen=True)
class OperationQc:
    checked: int
    defects: int
    operator_defects: int


@dataclass
class OperationShare:
    hours: Decimal = ZERO
    earned: Decimal = ZERO
    rub: Decimal = ZERO


@dataclass
class WeekShare:
    hours: Decimal = ZERO
    earned: Decimal = ZERO
    rub: Decimal = ZERO
    cost: Decimal = ZERO


@dataclass
class EmployeeStats:
    worked: Decimal = ZERO
    on_orders: Decimal = ZERO
    overhead: Decimal = ZERO
    repair: Decimal = ZERO
    idle: Decimal = ZERO
    training: Decimal = ZERO
    overtime: Decimal = ZERO
    absent_days: Decimal = ZERO
    earned: Decimal = ZERO
    rub: Decimal = ZERO
    cost: Decimal = ZERO
    checked: Decimal = ZERO
    defects: Decimal = ZERO
    operator_defects: Decimal = ZERO
    operations: dict[UUID, OperationShare] = field(default_factory=dict)
    weeks: dict[date, WeekShare] = field(default_factory=dict)


@dataclass
class EmployeeStatsResult:
    by_employee: dict[UUID, EmployeeStats]
    total_earned: Decimal
    # Освоено по операциям, на которые за период не разнесено ни часа — «не к кому
    # отнести» прототипа.
    unattributed: Decimal


def employee_stats(
    allocations: Iterable[Allocation],
    earned_by_operation: Mapping[UUID, Decimal],
    rate_by_operation: Mapping[UUID, Decimal],
    qc_by_operation: Mapping[UUID, OperationQc],
) -> EmployeeStatsResult:
    """Выработка сотрудников за период (§3.8, `empStats` прототипа).

    Освоение операции за период делится между исполнителями пропорционально их рабочим
    часам на этой операции за тот же период; в рублях — × ставка участка операции;
    стоимость часов — часы × ставка работника × коэффициент кода; брак операции — теми
    же долями. Нерабочие коды (отпуск, больничный…) — отсутствия в днях по 8 ч.
    """

    rows = list(allocations)
    operation_hours: dict[UUID, Decimal] = defaultdict(Decimal)
    for a in rows:
        if a.operation_id is not None and a.is_work:
            operation_hours[a.operation_id] += a.hours

    result: dict[UUID, EmployeeStats] = defaultdict(EmployeeStats)
    for a in rows:
        stats = result[a.employee_id]
        if not a.is_work:
            stats.absent_days += a.hours / HOURS_PER_DAY
            continue
        cost = a.hours * a.hourly_rate * a.cost_multiplier
        stats.worked += a.hours
        stats.cost += cost
        # Повышенный коэффициент — сверхурочные и работа в выходной (С, РВ).
        if a.cost_multiplier > 1:
            stats.overtime += a.hours
        week = stats.weeks.setdefault(week_start(a.date), WeekShare())
        week.hours += a.hours
        week.cost += cost

        if a.target == AllocationTarget.ORDER:
            stats.on_orders += a.hours
            if a.operation_id is None or not operation_hours[a.operation_id]:
                continue
            share = a.hours / operation_hours[a.operation_id]
            earned = earned_by_operation.get(a.operation_id, ZERO) * share
            rub = earned * rate_by_operation.get(a.operation_id, ZERO)
            stats.earned += earned
            stats.rub += rub
            week.earned += earned
            week.rub += rub
            op = stats.operations.setdefault(a.operation_id, OperationShare())
            op.hours += a.hours
            op.earned += earned
            op.rub += rub
            qc = qc_by_operation.get(a.operation_id)
            if qc is not None:
                stats.checked += Decimal(qc.checked) * share
                stats.defects += Decimal(qc.defects) * share
                stats.operator_defects += Decimal(qc.operator_defects) * share
        elif a.target == AllocationTarget.REPAIR:
            stats.repair += a.hours
        elif a.target == AllocationTarget.IDLE:
            stats.idle += a.hours
        elif a.target == AllocationTarget.TRAINING:
            stats.training += a.hours
        else:
            stats.overhead += a.hours

    total = sum(earned_by_operation.values(), ZERO)
    attributed = sum(
        (v for op_id, v in earned_by_operation.items() if operation_hours.get(op_id)), ZERO
    )
    return EmployeeStatsResult(
        by_employee=dict(result), total_earned=total, unattributed=total - attributed
    )
