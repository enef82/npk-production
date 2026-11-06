"""Чистые расчёты: прогноз ТО (`toState`), недельная сводка (`machWeek`), рабочие
дни — в Decimal (CLAUDE.md §8: количественные расчёты)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.equipment.calculations import (
    DEFAULT_AVG_RUN,
    add_working_days,
    average_run,
    forecast_maintenance,
    hours_between,
    summarize_week,
    week_start,
)
from src.equipment.models import MaintenanceState

FRIDAY = date(2026, 11, 6)


def test_рабочие_дни_пропускают_выходные() -> None:
    assert add_working_days(FRIDAY, 1) == date(2026, 11, 9)
    assert add_working_days(date(2026, 11, 7), 0) == date(2026, 11, 9)
    assert add_working_days(FRIDAY, 6) == date(2026, 11, 16)


def test_неделя_начинается_с_понедельника() -> None:
    assert week_start(date(2026, 11, 8)) == date(2026, 11, 2)


def test_то_просрочено_когда_наработка_превысила_интервал() -> None:
    forecast = forecast_maintenance(
        interval_hours=Decimal("250"),
        last_at_hours=Decimal("1000"),
        current_hours=Decimal("1262"),
        avg_run=Decimal("6"),
        today=FRIDAY,
    )
    assert forecast.next_at_hours == Decimal("1250.0")
    assert forecast.hours_left == Decimal("-12.0")
    assert forecast.state == MaintenanceState.OVERDUE
    assert forecast.due_date == FRIDAY


def test_то_скоро_когда_остаток_меньше_десятой_интервала() -> None:
    forecast = forecast_maintenance(
        interval_hours=Decimal("250"),
        last_at_hours=Decimal("1000"),
        current_hours=Decimal("1230"),
        avg_run=Decimal("6"),
        today=FRIDAY,
    )
    assert forecast.hours_left == Decimal("20.0")
    assert forecast.state == MaintenanceState.SOON
    # 20 ч / 6 ч в день = 3,33 → 4 рабочих дня от пятницы.
    assert forecast.due_date == date(2026, 11, 12)


def test_то_в_норме_и_без_прошлого_то_отсчёт_от_нуля() -> None:
    forecast = forecast_maintenance(
        interval_hours=Decimal("500"),
        last_at_hours=None,
        current_hours=Decimal("100"),
        avg_run=Decimal("0.1"),
        today=FRIDAY,
    )
    assert forecast.next_at_hours == Decimal("500.0")
    assert forecast.state == MaintenanceState.OK
    # Средняя ниже 0,5 ч берётся как 0,5: 400 / 0,5 = 800 рабочих дней.
    assert forecast.due_date == add_working_days(FRIDAY, 800)


def test_средняя_наработка_без_журнала_по_умолчанию_и_по_последним_двадцати() -> None:
    assert average_run([]) == DEFAULT_AVG_RUN
    runs = [Decimal("8")] * 20 + [Decimal("0")] * 5
    assert average_run(runs) == Decimal("8")


def test_загрузка_недели_работа_на_дни_с_записью_по_восемь_часов() -> None:
    summary = summarize_week(
        [
            (Decimal("6"), Decimal("1"), Decimal("1"), Decimal("0")),
            (Decimal("5.5"), Decimal("0.5"), Decimal("1"), Decimal("1")),
            (Decimal("4"), Decimal("0"), Decimal("4"), Decimal("0")),
        ]
    )
    assert summary.run == Decimal("15.5")
    assert summary.idle == Decimal("6")
    assert summary.days == 3
    assert summary.utilization == Decimal("0.6458")  # 15,5 / 24


def test_пустая_неделя_даёт_нулевую_загрузку() -> None:
    assert summarize_week([]).utilization == Decimal("0")


def test_простой_в_часах_с_одним_знаком() -> None:
    tz = ZoneInfo("Europe/Moscow")
    start = datetime(2026, 11, 2, 9, 0, tzinfo=tz)
    assert hours_between(start, datetime(2026, 11, 2, 11, 20, tzinfo=tz)) == Decimal("2.3")
    assert hours_between(start, start) == Decimal("0.0")
