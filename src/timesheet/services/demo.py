"""Демо-данные табеля (`seedTimesheet` прототипа) для `manage.py seed_demo`.

Сотрудников заводит не табель: профили создаются только для сотрудников `core.org`,
найденных по ФИО из набора прототипа (EMP); нет сотрудников — нет данных. Заказы и
участки `production` приходят аргументами (связку делают при слиянии модулей).
Детерминированно: один и тот же набор при одних и тех же входных данных. Повторный
вызов ничего не дублирует.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.org.models import Employee
from src.timesheet.calculations import (
    OVERTIME_CODE,
    PRESENCE_CODE,
    TRIP_CODE,
    is_weekend,
    month_start,
    split_plan_hours,
)
from src.timesheet.models import (
    AllocationSource,
    AllocationTarget,
    PeriodEventKind,
    PeriodStatus,
    TimeCode,
    TimesheetPeriod,
    TimesheetPeriodEvent,
    WorkAllocation,
    WorkerProfile,
)

# id прототипа, ФИО, подразделение прототипа, код участка прототипа, ставка ₽/ч
DEMO_WORKERS: tuple[tuple[str, str, str, str | None, str], ...] = (
    ("e01", "Белов С.А.", "okb", "kb", "1650"),
    ("e02", "Сидоров К.В.", "okb", "tp", "1550"),
    ("e03", "Лебедев П.Н.", "okb", "prog", "1750"),
    ("e04", "Гусев И.Д.", "meh", None, "1400"),
    ("e05", "Ткаченко Р.М.", "meh", "list", "1250"),
    ("e06", "Захаров А.П.", "meh", "meh", "1300"),
    ("e07", "Никитин В.С.", "meh", "meh", "1300"),
    ("e08", "Яковлев Д.И.", "meh", "svar", "1200"),
    ("e09", "Ершов М.А.", "meh", "svar", "1200"),
    ("e10", "Морозов Д.В.", "sbm", None, "1700"),
    ("e11", "Соколова Т.Н.", "sbm", "pok", "1000"),
    ("e12", "Фролов Е.Г.", "sbm", "izg", "1150"),
    ("e13", "Павлов С.К.", "sbm", "izg", "1150"),
    ("e14", "Ильин А.А.", "sbm", "sb", "1100"),
    ("e15", "Тарасов Н.Ю.", "sbm", "sb", "1100"),
    ("e16", "Комаров В.В.", "sbm", "em", "1200"),
    ("e17", "Беляев О.И.", "sbm", "em", "1200"),
    ("e18", "Кудрявцев Г.С.", "sbm", "em", "1200"),
    ("e19", "Орлова Н.В.", "otk", "otk", "1350"),
)
# Подразделения прототипа, чей табель прошлого месяца уже утверждён (остальные — на
# согласовании).
APPROVED_DEPARTMENTS = frozenset({"okb", "otk"})
EIGHT = Decimal("8")


def name_key(full_name: str) -> str:
    """«Белов С.А.» и «Белов Сергей Александрович» → «белов|са»."""

    parts = [p for p in re.split(r"[\s.]+", full_name.strip()) if p]
    if not parts:
        return ""
    return parts[0].lower() + "|" + "".join(p[0] for p in parts[1:3]).lower()


def _add_month(month: date, delta: int) -> date:
    index = month.year * 12 + month.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def _next_workday(day: date) -> date:
    while is_weekend(day):
        day += timedelta(days=1)
    return day


def _workdays_from(start: date, count: int) -> list[date]:
    days: list[date] = []
    day = start
    while len(days) < count:
        if not is_weekend(day):
            days.append(day)
        day += timedelta(days=1)
    return days


def seed_demo(
    orders: Sequence[tuple[UUID, UUID, UUID]] = (),
    *,
    work_centers: Mapping[str, UUID] | None = None,
    plan_windows: Mapping[UUID, tuple[date, date]] | None = None,
    today: date | None = None,
) -> int:
    """Профили и разноска за прошлый и текущий месяц. `orders` — (заказ, операция,
    участок) из `production`; `work_centers` — код участка прототипа (`kb`, `meh`, …)
    → id участка; `plan_windows` — операция → (плановое начало, окончание): если задано,
    в день разносятся только операции, чей план покрывает этот день, — иначе часы табеля
    лягут на операции, которые в эти даты не осваивались, и выработка сотрудников в
    аналитике окажется заниженной. Возвращает число созданных строк разноски."""

    today = today or timezone.localdate()
    by_key = {name_key(e.full_name): e for e in Employee.objects.all()}
    found: dict[str, tuple[Employee, str, UUID | None, Decimal]] = {}
    for proto_id, name, department, wc_code, rate in DEMO_WORKERS:
        employee = by_key.get(name_key(name))
        if employee is None:
            continue
        wc_id = (work_centers or {}).get(wc_code) if wc_code else None
        found[proto_id] = (employee, department, wc_id, Decimal(rate))
    if not found:
        return 0

    current = month_start(today)
    previous = _add_month(current, -1)
    month_end = _add_month(current, 1) - timedelta(days=1)

    with transaction.atomic():
        for employee, _, wc_id, hourly_rate in found.values():
            WorkerProfile.objects.get_or_create(
                employee=employee,
                defaults={"work_center_id": wc_id, "hourly_rate": hourly_rate},
            )
        employee_ids = [e.id for e, *_ in found.values()]
        if WorkAllocation.objects.filter(
            employee_id__in=employee_ids, date__gte=previous, date__lte=month_end
        ).exists():
            return 0

        codes = {c.code: c for c in TimeCode.objects.all()}
        rows: list[WorkAllocation] = []
        occupied: set[tuple[UUID, date]] = set()

        def add(
            proto_id: str,
            day: date,
            code: str,
            hours: Decimal,
            target: str = "",
            order: tuple[UUID, UUID, UUID] | None = None,
            source: AllocationSource = AllocationSource.MANUAL,
        ) -> None:
            if proto_id not in found or not (previous <= day <= month_end):
                return
            employee = found[proto_id][0]
            rows.append(
                WorkAllocation(
                    employee=employee,
                    date=day,
                    time_code=codes[code],
                    target=target,
                    order_id=order[0] if order else None,
                    operation_id=order[1] if order else None,
                    hours=hours,
                    source=source,
                )
            )
            occupied.add((employee.id, day))

        # Отсутствия из 1С.
        for proto_id, start, count, code in (
            ("e07", previous.replace(day=6), 3, "Б"),
            ("e17", today - timedelta(days=6), 9, "Б"),
            ("e09", previous.replace(day=20), 5, "ОТ"),
        ):
            for day in _workdays_from(start, count):
                add(proto_id, day, code, EIGHT)
        # Обучение ОТК и командировка программиста.
        add(
            "e19",
            _next_workday(previous.replace(day=14)),
            PRESENCE_CODE,
            EIGHT,
            AllocationTarget.TRAINING,
        )
        trip = _next_workday(previous.replace(day=22))
        for day in (trip + timedelta(days=k) for k in range(3)):
            if not is_weekend(day):
                add("e03", day, TRIP_CODE, EIGHT, AllocationTarget.OVERHEAD)

        # Рабочие дни до вчера — по «плану»: операции заказов на участке работника.
        by_wc: dict[UUID, list[tuple[UUID, UUID, UUID]]] = {}
        for order in orders:
            by_wc.setdefault(order[2], []).append(order)
        day = previous
        while day < today and day <= month_end:
            if not is_weekend(day):
                for index, (proto_id, (employee, _, wc_id, _)) in enumerate(found.items()):
                    if (employee.id, day) in occupied:
                        continue
                    ops = by_wc.get(wc_id, []) if wc_id else []
                    if plan_windows is not None:
                        ops = [
                            o
                            for o in ops
                            if o[1] in plan_windows
                            and plan_windows[o[1]][0] <= day <= plan_windows[o[1]][1]
                        ]
                    picked: list[tuple[UUID, UUID, UUID]] = []
                    if ops:
                        offset = (day.toordinal() + index) % len(ops)
                        count = 2 if len(ops) > 1 and (day.day + index) % 3 == 0 else 1
                        picked = [ops[(offset + k) % len(ops)] for k in range(count)]
                    shares, rest = split_plan_hours(len(picked))
                    for order, hours in zip(picked, shares, strict=True):
                        add(
                            proto_id,
                            day,
                            PRESENCE_CODE,
                            hours,
                            AllocationTarget.ORDER,
                            order,
                            AllocationSource.PLAN,
                        )
                    if rest > 0:
                        add(
                            proto_id,
                            day,
                            PRESENCE_CODE,
                            rest,
                            AllocationTarget.OVERHEAD,
                            source=AllocationSource.PLAN,
                        )
            day += timedelta(days=1)

        # Сверхурочные на электромонтаже — не хватает людей.
        for day in (today - timedelta(days=3), today - timedelta(days=2)):
            if is_weekend(day):
                continue
            for proto_id in ("e16", "e18"):
                if proto_id not in found:
                    continue
                first = next(
                    (r for r in rows if r.employee_id == found[proto_id][0].id and r.date == day),
                    None,
                )
                if first is None or not first.target:
                    continue
                rows.append(
                    WorkAllocation(
                        employee_id=first.employee_id,
                        date=day,
                        time_code=codes[OVERTIME_CODE],
                        target=first.target,
                        order_id=first.order_id,
                        operation_id=first.operation_id,
                        hours=Decimal("2"),
                        source=AllocationSource.MANUAL,
                    )
                )

        WorkAllocation.objects.bulk_create(rows)

        # Статусы табелей прошлого месяца.
        departments: dict[UUID, str] = {}
        for employee, proto_department, *_ in found.values():
            departments.setdefault(employee.department_id, proto_department)
        for department_id, proto_department in departments.items():
            if TimesheetPeriod.objects.filter(department_id=department_id, month=previous).exists():
                continue
            approved = proto_department in APPROVED_DEPARTMENTS
            period = TimesheetPeriod.objects.create(
                department_id=department_id,
                month=previous,
                status=PeriodStatus.APPROVED if approved else PeriodStatus.ON_REVIEW,
            )
            kinds = [PeriodEventKind.SUBMITTED] + ([PeriodEventKind.APPROVED] if approved else [])
            TimesheetPeriodEvent.objects.bulk_create(
                [TimesheetPeriodEvent(period=period, kind=k, version=1) for k in kinds]
            )
    return len(rows)
