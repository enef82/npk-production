"""Чистые функции графика: рабочие дни, длительность операции, прямой и обратный проход
сети, резерв, критический путь, нарушения связей, поиск цикла
(`docs/spec/00-prilozhenie-proizvodstvo.md` §2.1).

В ядре, а не в модуле: нужны `sales` (предварительный план заявки), `production` (план
заказа) и `analytics` (загрузка), а функциональный модуль не может импортировать чужие
внутренности (И1). Ни одного обращения к БД — по образцу `crm/calculations.py` ИС:
селектор или сервис собирает узлы и связи, здесь только арифметика.

Время — целые рабочие дни (пн–пт, праздников нет). Каждая дата переводится в номер
рабочего дня от опорного понедельника (`work_index`), арифметика идёт над номерами, как
`wIdx`/`fromW` прототипа. Операция длительностью `d`, начатая в день `s`, занимает дни
`s … s+d-1`; последователь без задержки начинается в день `s+d`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

# Понедельник — опорная точка нумерации рабочих дней. Любой понедельник подходит;
# номера бывают и отрицательными, `//` и `%` Python округляют вниз, что здесь и нужно.
_EPOCH = date(2024, 1, 1)
_HOURS_PER_DAY = Decimal(8)


def next_working_day(day: date) -> date:
    """Сам `day`, если он рабочий, иначе ближайший следующий понедельник."""

    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def work_index(day: date) -> int:
    """Номер рабочего дня. Выходной относится к следующему рабочему дню."""

    days = (next_working_day(day) - _EPOCH).days
    return (days // 7) * 5 + days % 7


def from_work_index(index: int) -> date:
    weeks, rest = divmod(index, 5)
    return _EPOCH + timedelta(days=weeks * 7 + rest)


def add_working_days(start: date, days: int) -> date:
    """Рабочий день номер `days` от `start` (день 0 — сам `start`, сдвинутый на ближайший
    рабочий). Отрицательное смещение — назад: нужно при сдвиге заказа на Ганте."""

    return from_work_index(work_index(start) + days)


def working_days_between(start: date, end: date) -> int:
    """Сколько рабочих дней от `start` до `end` — обратная к `add_working_days`.
    Отрицательно, если `end` раньше."""

    return work_index(end) - work_index(start)


def operation_duration(hours: Decimal, people: int, *, is_supply: bool) -> int:
    """Длительность операции в рабочих днях (§2.1): `max(1, ceil(н-ч / (8 × исполнителей)))`;
    у снабжения `hours` — срок поставки в днях, длительность `max(1, round(дни))`.
    Округление «половина вверх», как `Math.round` прототипа, а не банковское."""

    if isinstance(hours, float):
        raise TypeError("Трудоёмкость — Decimal, не float (И6)")
    if is_supply:
        return max(1, int(hours.quantize(Decimal(1), rounding=ROUND_HALF_UP)))
    crew = Decimal(max(1, people))
    return max(1, int((hours / (_HOURS_PER_DAY * crew)).quantize(Decimal(1), ROUND_CEILING)))


def finish_date(start: date, duration: int) -> date:
    """Последний занятый рабочий день операции."""

    return add_working_days(start, duration - 1)


# --- Сеть ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleNode:
    id: UUID
    duration: int
    # Начатая операция стоит по факту — её дата не пересчитывается.
    fixed_start: date | None = None
    # Ограничение «не ранее».
    not_before: date | None = None


@dataclass(frozen=True)
class ScheduleEdge:
    predecessor: UUID
    successor: UUID


@dataclass(frozen=True)
class NodeAnalysis:
    start: date
    finish: date
    slack: int
    is_critical: bool
    # Операция стоит раньше окончания предшественника (сдвинута вручную или начата
    # вопреки связи) — подсвечивается на Ганте.
    violates_dependency: bool


@dataclass(frozen=True)
class ScheduleAnalysis:
    nodes: dict[UUID, NodeAnalysis]
    start: date | None
    finish: date | None
    # Длина плана в рабочих днях от первого начала до последнего окончания включительно.
    length: int
    # Критические операции в топологическом порядке.
    critical_path: list[UUID]


class CycleError(ValueError):
    """Связи образуют цикл — расчёт невозможен. Сервисы связей не дают его создать;
    исключение — защита на случай данных, обошедших сервис."""


def find_cycle(node_ids: Iterable[UUID], edges: Sequence[ScheduleEdge]) -> list[UUID] | None:
    """Первый найденный цикл как список узлов (`[a, b, …, a]`) или `None`."""

    adjacency: dict[UUID, list[UUID]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        adjacency.setdefault(edge.predecessor, []).append(edge.successor)
        adjacency.setdefault(edge.successor, [])

    white, grey, black = 0, 1, 2
    color = dict.fromkeys(adjacency, white)
    parent: dict[UUID, UUID] = {}

    for root in adjacency:
        if color[root] != white:
            continue
        stack: list[tuple[UUID, int]] = [(root, 0)]
        color[root] = grey
        while stack:
            node, index = stack[-1]
            successors = adjacency[node]
            if index < len(successors):
                stack[-1] = (node, index + 1)
                nxt = successors[index]
                if color[nxt] == white:
                    color[nxt] = grey
                    parent[nxt] = node
                    stack.append((nxt, 0))
                elif color[nxt] == grey:
                    cycle = [nxt, node]
                    walker = node
                    while walker != nxt:
                        walker = parent[walker]
                        cycle.append(walker)
                    cycle.reverse()
                    return cycle
            else:
                color[node] = black
                stack.pop()
    return None


def _topological_order(nodes: Sequence[ScheduleNode], edges: Sequence[ScheduleEdge]) -> list[UUID]:
    indegree = {node.id: 0 for node in nodes}
    outgoing: dict[UUID, list[UUID]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.predecessor not in indegree or edge.successor not in indegree:
            raise ValueError("Связь ссылается на операцию вне сети")
        outgoing[edge.predecessor].append(edge.successor)
        indegree[edge.successor] += 1
    # Стабильный порядок — порядок узлов на входе: при равенстве результат не прыгает.
    queue = deque(node.id for node in nodes if indegree[node.id] == 0)
    order: list[UUID] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for successor in outgoing[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(order) != len(nodes):
        raise CycleError("Связи операций образуют цикл")
    return order


def _predecessors(
    nodes: Sequence[ScheduleNode], edges: Sequence[ScheduleEdge]
) -> dict[UUID, list[UUID]]:
    result: dict[UUID, list[UUID]] = {node.id: [] for node in nodes}
    for edge in edges:
        result[edge.successor].append(edge.predecessor)
    return result


def forward_pass(
    nodes: Sequence[ScheduleNode],
    edges: Sequence[ScheduleEdge],
    *,
    base: date,
    not_earlier_than: date | None = None,
) -> dict[UUID, date]:
    """Плановые начала (`schedule()` прототипа): не раньше `base` (начало заказа или
    заявки), не раньше окончания всех предшественников, не раньше «не ранее». Узел с
    `fixed_start` стоит по факту. `not_earlier_than` — «не раньше сегодня» для заказа
    в работе: не начатую операцию нельзя запланировать в прошлое."""

    by_id = {node.id: node for node in nodes}
    preds = _predecessors(nodes, edges)
    clamp = work_index(not_earlier_than) if not_earlier_than is not None else None
    starts: dict[UUID, int] = {}
    for node_id in _topological_order(nodes, edges):
        node = by_id[node_id]
        if node.fixed_start is not None:
            starts[node_id] = work_index(node.fixed_start)
            continue
        start = work_index(base)
        for pred_id in preds[node_id]:
            start = max(start, starts[pred_id] + by_id[pred_id].duration)
        if node.not_before is not None:
            start = max(start, work_index(node.not_before))
        if clamp is not None:
            start = max(start, clamp)
        starts[node_id] = start
    return {node_id: from_work_index(index) for node_id, index in starts.items()}


def analyze(
    nodes: Sequence[ScheduleNode],
    edges: Sequence[ScheduleEdge],
    starts: Mapping[UUID, date],
) -> ScheduleAnalysis:
    """Обратный проход по уже стоящим датам (`cpm()` прототипа): поздние сроки, резерв,
    критичность (резерв ≤ 0), нарушения связей. Узлы без даты в `starts` — ошибка:
    план либо есть у всех операций, либо его нет."""

    if not nodes:
        return ScheduleAnalysis(nodes={}, start=None, finish=None, length=0, critical_path=[])
    by_id = {node.id: node for node in nodes}
    order = _topological_order(nodes, edges)
    preds = _predecessors(nodes, edges)
    succs: dict[UUID, list[UUID]] = {node.id: [] for node in nodes}
    for edge in edges:
        succs[edge.predecessor].append(edge.successor)

    early_start = {node.id: work_index(starts[node.id]) for node in nodes}
    early_finish = {nid: early_start[nid] + by_id[nid].duration - 1 for nid in early_start}
    end = max(early_finish.values())
    begin = min(early_start.values())

    late_start: dict[UUID, int] = {}
    for node_id in reversed(order):
        late_finish = min(late_start[s] for s in succs[node_id]) - 1 if succs[node_id] else end
        late_start[node_id] = late_finish - by_id[node_id].duration + 1

    result: dict[UUID, NodeAnalysis] = {}
    for node_id in order:
        slack = late_start[node_id] - early_start[node_id]
        result[node_id] = NodeAnalysis(
            start=from_work_index(early_start[node_id]),
            finish=from_work_index(early_finish[node_id]),
            slack=slack,
            is_critical=slack <= 0,
            violates_dependency=any(
                early_start[node_id] <= early_finish[pred] for pred in preds[node_id]
            ),
        )
    return ScheduleAnalysis(
        nodes=result,
        start=from_work_index(begin),
        finish=from_work_index(end),
        length=end - begin + 1,
        critical_path=[node_id for node_id in order if result[node_id].is_critical],
    )


def compute_schedule(
    nodes: Sequence[ScheduleNode],
    edges: Sequence[ScheduleEdge],
    *,
    base: date,
    not_earlier_than: date | None = None,
) -> ScheduleAnalysis:
    """Прямой и обратный проход за один вызов."""

    starts = forward_pass(nodes, edges, base=base, not_earlier_than=not_earlier_than)
    return analyze(nodes, edges, starts)


# --- Здоровье плана ------------------------------------------------------------------


class HealthColor(StrEnum):
    GREEN = "g"
    YELLOW = "y"
    RED = "r"
    NONE = "n"


@dataclass(frozen=True)
class Health:
    color: HealthColor
    # Что показать на карточке: «late» — позже срока на `days`, «lagging» — есть
    # отставание, «tight» — запас `days` ≤ 4, «ok» — укладываемся, «no_plan», «done».
    status: str
    days: int


_TIGHT_SLACK_DAYS = 4


def assess_health(
    *,
    finish: date | None,
    due: date | None,
    has_plan: bool,
    is_done: bool,
    is_lagging: bool,
) -> Health:
    """`health()` прототипа. Дни — календарные (`diffD`), как на карточке прототипа.
    `is_lagging` — у заказа в работе есть не выполненная операция, чьё плановое
    окончание уже прошло; для заявки всегда `False`."""

    if is_done:
        return Health(HealthColor.GREEN, "done", 0)
    if not has_plan or finish is None or due is None:
        return Health(HealthColor.NONE, "no_plan", 0)
    if finish > due:
        return Health(HealthColor.RED, "late", (finish - due).days)
    if is_lagging:
        return Health(HealthColor.YELLOW, "lagging", 0)
    reserve = (due - finish).days
    if reserve <= _TIGHT_SLACK_DAYS:
        return Health(HealthColor.YELLOW, "tight", reserve)
    return Health(HealthColor.GREEN, "ok", reserve)
