"""Чистые функции графика (`src/core/common/scheduling.py`) — без БД."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.core.common.scheduling import (
    CycleError,
    HealthColor,
    ScheduleEdge,
    ScheduleNode,
    add_working_days,
    analyze,
    assess_health,
    compute_schedule,
    find_cycle,
    finish_date,
    forward_pass,
    next_working_day,
    operation_duration,
    working_days_between,
)

MONDAY = date(2026, 11, 9)
FRIDAY = date(2026, 11, 13)
SATURDAY = date(2026, 11, 14)


def test_выходной_переносится_на_понедельник() -> None:
    assert next_working_day(SATURDAY) == date(2026, 11, 16)
    assert next_working_day(MONDAY) == MONDAY


def test_добавление_рабочих_дней_пропускает_выходные() -> None:
    assert add_working_days(MONDAY, 0) == MONDAY
    assert add_working_days(MONDAY, 4) == FRIDAY
    assert add_working_days(MONDAY, 5) == date(2026, 11, 16)
    assert add_working_days(SATURDAY, 0) == date(2026, 11, 16)


def test_отрицательное_смещение_идёт_назад_через_выходные() -> None:
    assert add_working_days(date(2026, 11, 16), -1) == FRIDAY
    assert add_working_days(MONDAY, -5) == date(2026, 11, 2)


def test_число_рабочих_дней_обратно_добавлению() -> None:
    for offset in (-7, -1, 0, 1, 3, 12):
        assert working_days_between(MONDAY, add_working_days(MONDAY, offset)) == offset


def test_длительность_операции_по_трудоёмкости_и_исполнителям() -> None:
    assert operation_duration(Decimal("40"), 2, is_supply=False) == 3  # 40 / 16 = 2,5 → 3
    assert operation_duration(Decimal("16"), 2, is_supply=False) == 1
    assert operation_duration(Decimal("0.4"), 1, is_supply=False) == 1
    assert operation_duration(Decimal("0"), 1, is_supply=False) == 1


def test_длительность_снабжения_это_срок_поставки_с_округлением_половины_вверх() -> None:
    assert operation_duration(Decimal("15"), 0, is_supply=True) == 15
    assert operation_duration(Decimal("2.5"), 0, is_supply=True) == 3
    assert operation_duration(Decimal("0.2"), 0, is_supply=True) == 1


def test_float_в_трудоёмкости_запрещён() -> None:
    with pytest.raises(TypeError):
        operation_duration(1.5, 1, is_supply=False)  # type: ignore[arg-type]


def test_окончание_операции_последний_занятый_день() -> None:
    assert finish_date(MONDAY, 1) == MONDAY
    assert finish_date(FRIDAY, 2) == date(2026, 11, 16)


def _chain() -> tuple[list[ScheduleNode], list[ScheduleEdge], list[UUID]]:
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    nodes = [
        ScheduleNode(id=a, duration=2),
        ScheduleNode(id=b, duration=3),
        ScheduleNode(id=c, duration=1),
        ScheduleNode(id=d, duration=1),
    ]
    # a → b → d, a → c → d: c идёт параллельно b и имеет резерв.
    edges = [
        ScheduleEdge(a, b),
        ScheduleEdge(a, c),
        ScheduleEdge(b, d),
        ScheduleEdge(c, d),
    ]
    return nodes, edges, [a, b, c, d]


def test_прямой_проход_ставит_последователя_после_окончания_предшественника() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    starts = forward_pass(nodes, edges, base=MONDAY)
    assert starts[a] == MONDAY
    assert starts[b] == date(2026, 11, 11)
    assert starts[c] == date(2026, 11, 11)
    assert starts[d] == date(2026, 11, 16)  # b занимает ср–пт, d — понедельник


def test_не_ранее_сдвигает_операцию_и_её_последователей() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    nodes[2] = ScheduleNode(id=c, duration=1, not_before=date(2026, 11, 18))
    starts = forward_pass(nodes, edges, base=MONDAY)
    assert starts[c] == date(2026, 11, 18)
    assert starts[d] == date(2026, 11, 19)


def test_начатая_операция_стоит_по_факту() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    nodes[0] = ScheduleNode(id=a, duration=2, fixed_start=date(2026, 11, 2))
    starts = forward_pass(nodes, edges, base=MONDAY)
    assert starts[a] == date(2026, 11, 2)
    # Последователь не раньше начала заказа, даже если предшественник кончился раньше.
    assert starts[b] == MONDAY


def test_не_начатая_операция_не_планируется_раньше_сегодня() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    today = date(2026, 11, 12)
    starts = forward_pass(nodes, edges, base=MONDAY, not_earlier_than=today)
    assert starts[a] == today
    assert starts[b] == date(2026, 11, 16)


def test_обратный_проход_находит_резерв_и_критический_путь() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    result = compute_schedule(nodes, edges, base=MONDAY)
    assert result.nodes[c].slack == 2
    assert not result.nodes[c].is_critical
    assert result.critical_path == [a, b, d]
    assert result.start == MONDAY
    assert result.finish == date(2026, 11, 16)
    assert result.length == 6


def test_операция_раньше_окончания_предшественника_отмечается_нарушением() -> None:
    nodes, edges, (a, b, c, d) = _chain()
    starts = forward_pass(nodes, edges, base=MONDAY)
    starts[b] = date(2026, 11, 10)  # a ещё идёт во вторник
    result = analyze(nodes, edges, starts)
    assert result.nodes[b].violates_dependency
    assert not result.nodes[c].violates_dependency


def test_пустая_сеть_без_плана() -> None:
    result = analyze([], [], {})
    assert result.start is None
    assert result.length == 0


def test_цикл_находится_и_ломает_расчёт() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    edges = [ScheduleEdge(a, b), ScheduleEdge(b, c), ScheduleEdge(c, a)]
    cycle = find_cycle([a, b, c], edges)
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert find_cycle([a, b, c], edges[:2]) is None
    nodes = [ScheduleNode(id=x, duration=1) for x in (a, b, c)]
    with pytest.raises(CycleError):
        forward_pass(nodes, edges, base=MONDAY)


def test_здоровье_плана() -> None:
    finish = date(2026, 11, 20)
    late = assess_health(
        finish=finish, due=date(2026, 11, 17), has_plan=True, is_done=False, is_lagging=False
    )
    assert (late.color, late.status, late.days) == (HealthColor.RED, "late", 3)

    tight = assess_health(
        finish=finish, due=date(2026, 11, 23), has_plan=True, is_done=False, is_lagging=False
    )
    assert (tight.color, tight.days) == (HealthColor.YELLOW, 3)

    ok = assess_health(
        finish=finish, due=date(2026, 12, 1), has_plan=True, is_done=False, is_lagging=False
    )
    assert ok.color == HealthColor.GREEN

    lagging = assess_health(
        finish=finish, due=date(2026, 12, 1), has_plan=True, is_done=False, is_lagging=True
    )
    assert lagging.status == "lagging"

    assert (
        assess_health(finish=None, due=None, has_plan=False, is_done=False, is_lagging=False).color
        == HealthColor.NONE
    )
    assert (
        assess_health(finish=finish, due=None, has_plan=True, is_done=True, is_lagging=False).status
        == "done"
    )
