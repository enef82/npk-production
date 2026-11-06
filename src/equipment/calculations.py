"""Чистые расчёты модуля «Оборудование и ТО» — без БД (CLAUDE.md §5): прогноз ТО
(`toState` прототипа), недельная сводка (`machWeek`), рабочие дни.

Рабочие дни — пн–пт, праздников нет (спецификация §2.1). Своя функция, а не
`core.common.scheduling`: на момент написания модуля ядро её ещё не содержит; при
появлении — заменить вызовом ядра.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from src.equipment.models import MaintenanceState

HOURS_PER_SHIFT = Decimal("8")
# Средняя наработка, если журнала ещё нет, и нижняя граница средней — как в прототипе
# (`avgRun`: 4 ч; `Math.max(.5, avgRun)`), чтобы прогноз не уходил в бесконечность.
DEFAULT_AVG_RUN = Decimal("4")
MIN_AVG_RUN = Decimal("0.5")
SOON_SHARE = Decimal("0.1")
AVG_RUN_WINDOW = 20

ONE_DECIMAL = Decimal("0.1")


def round1(value: Decimal) -> Decimal:
    return value.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def is_working_day(day: date) -> bool:
    return day.weekday() < 5


def next_working_day(day: date) -> date:
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def add_working_days(day: date, count: int) -> date:
    """`addWork` прототипа: от ближайшего рабочего дня вперёд на `count` рабочих."""

    day = next_working_day(day)
    while count > 0:
        day += timedelta(days=1)
        if is_working_day(day):
            count -= 1
    return day


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def average_run(last_runs: list[Decimal]) -> Decimal:
    """Средняя работа за последние `AVG_RUN_WINDOW` записей журнала."""

    runs = last_runs[:AVG_RUN_WINDOW]
    if not runs:
        return DEFAULT_AVG_RUN
    return sum(runs, Decimal("0")) / len(runs)


@dataclass(frozen=True)
class MaintenanceForecast:
    next_at_hours: Decimal
    hours_left: Decimal
    due_date: date
    state: MaintenanceState


def forecast_maintenance(
    *,
    interval_hours: Decimal,
    last_at_hours: Decimal | None,
    current_hours: Decimal,
    avg_run: Decimal,
    today: date,
) -> MaintenanceForecast:
    """Следующее ТО = (последнее при … или 0) + интервал; остаток; дата — по средней
    наработке; состояние: просрочено (остаток ≤ 0) / скоро (< 10 % интервала) / норма."""

    next_at = round1((last_at_hours or Decimal("0")) + interval_hours)
    left = round1(next_at - current_hours)
    per_day = max(MIN_AVG_RUN, avg_run)
    days = int((max(Decimal("0"), left) / per_day).to_integral_value(rounding=ROUND_CEILING))
    if left <= 0:
        return MaintenanceForecast(next_at, left, today, MaintenanceState.OVERDUE)
    state = MaintenanceState.SOON if left < interval_hours * SOON_SHARE else MaintenanceState.OK
    return MaintenanceForecast(next_at, left, add_working_days(today, days), state)


@dataclass(frozen=True)
class WeekSummary:
    run: Decimal
    setup: Decimal
    idle: Decimal
    down: Decimal
    days: int
    utilization: Decimal  # доля, 0…1, 4 знака


def summarize_week(rows: list[tuple[Decimal, Decimal, Decimal, Decimal]]) -> WeekSummary:
    """`machWeek`: суммы и коэффициент загрузки `работа / (дней с записью × 8)`."""

    zero = Decimal("0")
    run = sum((row[0] for row in rows), zero)
    setup = sum((row[1] for row in rows), zero)
    idle = sum((row[2] for row in rows), zero)
    down = sum((row[3] for row in rows), zero)
    days = len(rows)
    utilization = (
        (run / (days * HOURS_PER_SHIFT)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if days
        else zero
    )
    return WeekSummary(run, setup, idle, down, days, utilization)


def hours_between(start: datetime, finish: datetime) -> Decimal:
    """Простой в часах между двумя моментами, 1 знак, не меньше нуля (`repDown`)."""

    seconds = Decimal(int((finish - start).total_seconds()))
    return max(Decimal("0"), round1(seconds / Decimal("3600")))
