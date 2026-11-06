"""Чистые расчёты аналитики — точные `Decimal` (CLAUDE.md §8: денежные и количественные
расчёты): распределение часов по дням и неделям, остаток, выработка сотрудников."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from src.analytics import calculations as calc
from src.analytics.calculations import Allocation, OperationQc, SpreadOp
from src.timesheet.facade import AllocationTarget

WC = uuid4()


def test_неделя_и_месяц_по_дате() -> None:
    assert calc.week_start(date(2026, 11, 8)) == date(2026, 11, 2)  # воскресенье
    assert calc.add_months(date(2026, 11, 1), 2) == date(2027, 1, 1)
    assert calc.add_months(date(2026, 1, 1), -2) == date(2025, 11, 1)
    assert calc.month_end(date(2026, 2, 1)) == date(2026, 2, 28)


def test_рабочие_дни_месяца_без_выходных() -> None:
    assert calc.working_days_in_month(date(2026, 11, 1)) == 21
    assert calc.working_days_in_month(date(2026, 2, 1)) == 20


def test_дни_операции_пропускают_выходные() -> None:
    days = calc.operation_days(date(2026, 11, 5), date(2026, 11, 10))
    assert days == [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)]


def test_часы_операции_через_выходные_делятся_между_неделями_поровну_по_дням() -> None:
    # Чт, Пт — неделя 02.11; Пн, Вт — неделя 09.11: 10 ч ÷ 4 дня = 2,5 ч в день.
    result = calc.spread_by_week(
        [SpreadOp(WC, Decimal("10"), date(2026, 11, 5), date(2026, 11, 10))]
    )
    assert result == {
        (date(2026, 11, 2), WC): Decimal("5"),
        (date(2026, 11, 9), WC): Decimal("5"),
    }


def test_остаток_по_месяцам_только_на_будущие_дни() -> None:
    # Пт 27.11 и Пн 30.11 уже позади (не раньше 01.12), остаются 01–02.12.
    op = SpreadOp(WC, Decimal("12"), date(2026, 11, 26), date(2026, 12, 2))
    result = calc.spread_by_month([op], not_before=date(2026, 12, 1))
    assert result == {(date(2026, 12, 1), WC): Decimal("12")}


def test_просроченная_операция_целиком_ложится_на_сегодня() -> None:
    op = SpreadOp(WC, Decimal("7"), date(2026, 10, 1), date(2026, 10, 2))
    result = calc.spread_by_month([op], not_before=date(2026, 11, 6))
    assert result == {(date(2026, 11, 1), WC): Decimal("7")}


def test_остаток_операции_по_прогрессу() -> None:
    assert calc.remaining_hours(Decimal("16"), 30) == Decimal("11.2")
    assert calc.remaining_hours(Decimal("16"), 100) == Decimal("0")


def test_проценты_без_базы_пусто_а_не_ноль() -> None:
    assert calc.pct(Decimal("12"), Decimal("16")) == Decimal("75.0")
    assert calc.pct(Decimal("1"), Decimal("3")) == Decimal("33.3")
    assert calc.pct(Decimal("5"), Decimal("0")) is None
    assert calc.ratio(Decimal("11250"), Decimal("6000")) == Decimal("1.88")


def _alloc(
    employee: object,
    hours: str,
    *,
    op: object = None,
    target: str = AllocationTarget.ORDER,
    rate: str = "1000",
    multiplier: str = "1",
    is_work: bool = True,
    day: date = date(2026, 11, 3),
) -> Allocation:
    return Allocation(
        employee_id=employee,  # type: ignore[arg-type]
        date=day,
        is_work=is_work,
        cost_multiplier=Decimal(multiplier),
        target=target,
        operation_id=op,  # type: ignore[arg-type]
        hours=Decimal(hours),
        hourly_rate=Decimal(rate),
    )


def test_освоение_операции_делится_по_часам_исполнителей_и_оценивается_по_ставке_участка() -> None:
    a, b, op = uuid4(), uuid4(), uuid4()
    result = calc.employee_stats(
        [
            _alloc(a, "6", op=op, rate="1000"),
            _alloc(b, "2", op=op, rate="1200", multiplier="1.5"),
        ],
        earned_by_operation={op: Decimal("10")},
        rate_by_operation={op: Decimal("1500")},
        qc_by_operation={op: OperationQc(checked=4, defects=2, operator_defects=2)},
    )
    sa, sb = result.by_employee[a], result.by_employee[b]

    assert (sa.earned, sb.earned) == (Decimal("7.5"), Decimal("2.5"))
    assert (sa.rub, sb.rub) == (Decimal("11250"), Decimal("3750"))
    # Стоимость часов: часы × ставка работника × коэффициент кода.
    assert (sa.cost, sb.cost) == (Decimal("6000"), Decimal("3600"))
    assert calc.ratio(sa.rub, sa.cost) == Decimal("1.88")
    assert calc.ratio(sb.rub, sb.cost) == Decimal("1.04")
    assert (sa.overtime, sb.overtime) == (Decimal("0"), Decimal("2"))
    # Брак операции — теми же долями, отдельно по вине оператора.
    assert (sa.checked, sa.defects, sa.operator_defects) == (
        Decimal("3"),
        Decimal("1.5"),
        Decimal("1.5"),
    )
    assert sb.defects == Decimal("0.5")
    assert sa.operations[op].earned == Decimal("7.5")
    assert sa.weeks[date(2026, 11, 2)].rub == Decimal("11250")
    assert result.total_earned == Decimal("10")
    assert result.unattributed == Decimal("0")


def test_структура_времени_и_отсутствия() -> None:
    a = uuid4()
    stats = calc.employee_stats(
        [
            _alloc(a, "4", target=AllocationTarget.OVERHEAD),
            _alloc(a, "2", target=AllocationTarget.IDLE),
            _alloc(a, "1", target=AllocationTarget.REPAIR),
            _alloc(a, "1", target=AllocationTarget.TRAINING),
            _alloc(a, "8", is_work=False, day=date(2026, 11, 4)),
            _alloc(a, "4", is_work=False, day=date(2026, 11, 5)),
        ],
        earned_by_operation={},
        rate_by_operation={},
        qc_by_operation={},
    ).by_employee[a]

    assert stats.worked == Decimal("8")
    assert (stats.overhead, stats.idle, stats.repair, stats.training) == (
        Decimal("4"),
        Decimal("2"),
        Decimal("1"),
        Decimal("1"),
    )
    assert stats.on_orders == Decimal("0")
    # Отсутствия — дни по 8 ч, стоимость за них не начисляется.
    assert stats.absent_days == Decimal("1.5")
    assert stats.cost == Decimal("8000")


def test_освоение_без_часов_в_табеле_некому_отнести() -> None:
    a, op, orphan = uuid4(), uuid4(), uuid4()
    result = calc.employee_stats(
        [_alloc(a, "8", op=op)],
        earned_by_operation={op: Decimal("6"), orphan: Decimal("3.5")},
        rate_by_operation={op: Decimal("1000"), orphan: Decimal("1000")},
        qc_by_operation={},
    )
    assert result.by_employee[a].earned == Decimal("6")
    assert result.total_earned == Decimal("9.5")
    assert result.unattributed == Decimal("3.5")


def test_часы_на_заказе_без_операции_не_дают_освоения() -> None:
    a = uuid4()
    stats = calc.employee_stats(
        [_alloc(a, "8")], earned_by_operation={}, rate_by_operation={}, qc_by_operation={}
    ).by_employee[a]
    assert (stats.on_orders, stats.earned, stats.rub) == (Decimal("8"), Decimal("0"), Decimal("0"))
