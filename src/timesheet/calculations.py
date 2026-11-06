"""Чистые расчёты табеля без обращений к БД (CLAUDE.md §5): календарь месяца, проверки
перед подачей (`tsChecks` прототипа), деление дня по плану (`autoFillDay`), вытеснение
строк часами ремонта (`repToTimesheet`), пакеты для 1С (`buildPackages`).

Селекторы и сервисы загружают данные и зовут эти функции — так правила прототипа
тестируются точными числами без фабрик, а сервисный слой меняет только состояние.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from src.timesheet.models.choices import AllocationTarget, PackageType

HOURS_Q = Decimal("0.01")
SHARE_Q = Decimal("0.0001")
DAY_NORM = Decimal("8")
DAY_LIMIT = Decimal("24")
PLAN_STEP = Decimal("0.5")

# Коды, на которых держатся правила прототипа. Это значения справочника, а не статусы:
# справочник засеян миграцией `0002_seed_time_codes`, коды не переименовываются.
PRESENCE_CODE = "Я"
OVERTIME_CODE = "С"
WEEKEND_WORK_CODE = "РВ"
TRIP_CODE = "К"

# Накладные и простой вытесняются часами ремонта первыми (`repToTimesheet`).
SOFT_TARGETS = frozenset({AllocationTarget.OVERHEAD, AllocationTarget.IDLE})


def quantize_hours(value: Decimal) -> Decimal:
    return value.quantize(HOURS_Q, rounding=ROUND_HALF_UP)


def format_hours(value: Decimal) -> str:
    """«8», «2.5» — для текста проверок; в пакетах 1С часы идут строкой с двумя знаками."""

    text = format(quantize_hours(value), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


# --- Календарь ---------------------------------------------------------------------


def month_start(day: date) -> date:
    return day.replace(day=1)


def month_days(month: date) -> list[date]:
    count = calendar.monthrange(month.year, month.month)[1]
    return [month.replace(day=n) for n in range(1, count + 1)]


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def last_closed_day(month: date, today: date) -> date | None:
    """Последний день месяца, который уже должен быть закрыт: весь месяц для прошлого,
    вчера для текущего, ни одного для будущего."""

    if month < month_start(today):
        return month_days(month)[-1]
    if month == month_start(today):
        yesterday = today - timedelta(days=1)
        return yesterday if yesterday >= month else None
    return None


def working_days_until(month: date, last: date | None) -> list[date]:
    if last is None:
        return []
    return [d for d in month_days(month) if not is_weekend(d) and d <= last]


# --- Деление дня по плану -------------------------------------------------------------


@dataclass(frozen=True)
class PlannedOp:
    """Плановая операция участка на день — то, что вернёт
    `production.facade.list_planned_operations` (до слияния — аргумент сервиса)."""

    operation_id: UUID
    order_id: UUID
    label: str


def split_plan_hours(operations_count: int) -> tuple[list[Decimal], Decimal]:
    """8 ч поровну на операции с шагом 0,5 ч вниз; остаток — накладные
    (спецификация §3.5). Без операций весь день — накладные."""

    if operations_count <= 0:
        return [], DAY_NORM
    share = (DAY_NORM / operations_count / PLAN_STEP).to_integral_value(ROUND_DOWN) * PLAN_STEP
    shares = [share] * operations_count
    return shares, DAY_NORM - share * operations_count


# --- Вытеснение часами ремонта ----------------------------------------------------------


@dataclass(frozen=True)
class DisplaceableRow:
    id: UUID
    target: str
    hours: Decimal


def plan_repair_displacement(rows: Sequence[DisplaceableRow], need: Decimal) -> dict[UUID, Decimal]:
    """Новые часы строк дня после вытеснения `need` часов ремонтом (0 — строку удалить).

    Порядок прототипа: сначала накладные и простой, затем остальные разносимые строки,
    внутри группы — от больших часов к меньшим. Передавать только разносимые строки,
    кроме уже ремонтных."""

    ordered = sorted(rows, key=lambda r: (r.target not in SOFT_TARGETS, -r.hours))
    result: dict[UUID, Decimal] = {}
    left = need
    for row in ordered:
        if left <= 0:
            break
        taken = min(row.hours, left)
        result[row.id] = row.hours - taken
        left -= taken
    return result


# --- Проверки перед подачей ---------------------------------------------------------


@dataclass(frozen=True)
class CheckWorker:
    employee_id: UUID
    full_name: str
    has_work_center: bool
    active_from: date
    active_to: date | None


@dataclass(frozen=True)
class AllocationFact:
    employee_id: UUID
    date: date
    code: str
    is_work: bool
    target: str
    hours: Decimal


@dataclass(frozen=True)
class Check:
    is_blocking: bool
    text: str
    employee_id: UUID | None = None


def _day_list(days: Iterable[date]) -> str:
    return ", ".join(str(d.day) for d in days)


def compute_checks(
    workers: Sequence[CheckWorker],
    facts: Sequence[AllocationFact],
    month: date,
    today: date,
) -> list[Check]:
    days = month_days(month)
    last = last_closed_day(month, today)
    closed_days = working_days_until(month, last)

    by_employee: dict[UUID, list[AllocationFact]] = defaultdict(list)
    for fact in facts:
        by_employee[fact.employee_id].append(fact)

    out: list[Check] = []
    for worker in workers:
        rows = by_employee.get(worker.employee_id, [])
        per_day: dict[date, Decimal] = defaultdict(Decimal)
        for row in rows:
            per_day[row.date] += row.hours

        missing = [
            d
            for d in closed_days
            if d >= worker.active_from
            and (worker.active_to is None or d <= worker.active_to)
            and d not in per_day
        ]
        if missing:
            out.append(
                Check(
                    True,
                    f"{worker.full_name}: не закрыты дни {_day_list(missing)}",
                    worker.employee_id,
                )
            )

        over = sorted(d for d, h in per_day.items() if h > DAY_LIMIT)
        if over:
            out.append(
                Check(
                    True,
                    f"{worker.full_name}: больше 24 ч в день ({_day_list(over)})",
                    worker.employee_id,
                )
            )

        work = sum((r.hours for r in rows if r.is_work), Decimal("0"))
        absence = sum(
            (r.hours for r in rows if not r.is_work and last is not None and r.date <= last),
            Decimal("0"),
        )
        norm = DAY_NORM * len(closed_days)
        marked = any(r.code in (OVERTIME_CODE, WEEKEND_WORK_CODE) for r in rows)
        if work + absence > norm and not marked:
            out.append(
                Check(
                    False,
                    f"{worker.full_name}: часов больше нормы без пометки «С» или «РВ»",
                    worker.employee_id,
                )
            )

        overhead = sum(
            (r.hours for r in rows if r.target == AllocationTarget.OVERHEAD), Decimal("0")
        )
        if worker.has_work_center and work > 0 and overhead / work > Decimal("0.5"):
            percent = (overhead / work * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            out.append(
                Check(
                    False,
                    f"{worker.full_name}: {percent}% часов на накладные — проверьте разноску",
                    worker.employee_id,
                )
            )

    rest = [d for d in days if not is_weekend(d) and (last is None or d > last)]
    if rest:
        out.append(Check(True, f"Месяц не закончен: осталось {len(rest)} рабочих дней"))
    return out


# --- Пакеты для 1С ------------------------------------------------------------------


@dataclass(frozen=True)
class PackageFact:
    personnel_no: str
    date: date
    code: str
    is_work: bool
    target: str
    order_id: UUID | None
    hours: Decimal


def analytics_for(
    target: str, order_id: UUID | None, department_code: str, order_numbers: Mapping[UUID, str]
) -> str:
    """Аналитика 1С (`objAnalytics`): номер заказа, OVH-/REP-<код подразделения>, TRN, IDLE.
    Номер заказа, которого не знает `production`, заменяется его UUID — строка не
    теряется и находится по идентификатору."""

    if target == AllocationTarget.ORDER and order_id is not None:
        return order_numbers.get(order_id, str(order_id))
    if target == AllocationTarget.REPAIR:
        return f"REP-{department_code}"
    if target == AllocationTarget.TRAINING:
        return "TRN"
    if target == AllocationTarget.IDLE:
        return "IDLE"
    return f"OVH-{department_code}"


def _shares(hours: list[Decimal]) -> list[Decimal]:
    """Доли, округлённые до 4 знаков, с суммой ровно 1: остаток округления ложится на
    самую большую строку — 1С распределяет по долям всю сумму, без копеек «в никуда»."""

    total = sum(hours, Decimal("0"))
    shares = [(h / total).quantize(SHARE_Q, rounding=ROUND_HALF_UP) for h in hours]
    diff = Decimal("1") - sum(shares, Decimal("0"))
    if diff:
        biggest = max(range(len(hours)), key=lambda i: hours[i])
        shares[biggest] += diff
    return shares


def build_packages(
    facts: Sequence[PackageFact],
    *,
    month: date,
    department_code: str,
    version: int,
    order_numbers: Mapping[UUID, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Два пакета обмена (ИС ADR 0002 — обмен файлом): табель по видам времени и база
    распределения затрат. Часы и доли — строками десятичных чисел (И6: JSON не знает
    `Decimal`, `float` запрещён). Суммы начисляет 1С."""

    entries: dict[tuple[str, date, str], Decimal] = defaultdict(Decimal)
    by_analytics: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for fact in facts:
        entries[(fact.personnel_no, fact.date, fact.code)] += fact.hours
        if fact.is_work:
            key = analytics_for(fact.target, fact.order_id, department_code, order_numbers)
            by_analytics[fact.personnel_no][key] += fact.hours

    rows: list[dict[str, str]] = []
    for personnel_no in sorted(by_analytics):
        items = sorted(by_analytics[personnel_no].items())
        shares = _shares([h for _, h in items])
        rows.extend(
            {
                "employee_code": personnel_no,
                "analytics": key,
                "hours": str(quantize_hours(h)),
                "share": str(share),
            }
            for (key, h), share in zip(items, shares, strict=True)
        )

    base: dict[str, Any] = {
        "period": {"year": month.year, "month": month.month},
        "department_code": department_code,
        "version": version,
    }
    timesheet = {
        "package_type": PackageType.TIMESHEET.value,
        **base,
        "entries": [
            {
                "employee_code": personnel_no,
                "date": day.isoformat(),
                "time_code": code,
                "hours": str(quantize_hours(h)),
            }
            for (personnel_no, day, code), h in sorted(entries.items())
        ],
    }
    cost_allocation = {"package_type": PackageType.COST_ALLOCATION.value, **base, "rows": rows}
    return timesheet, cost_allocation
