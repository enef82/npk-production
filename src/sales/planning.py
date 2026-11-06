"""Сеть операций калькуляции для `core.common.scheduling`. Без запросов к БД: участки —
`production.facade.list_work_centers()`, загруженные вызывающим один раз."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from uuid import UUID

from src.core.common.scheduling import (
    ScheduleEdge,
    ScheduleNode,
    finish_date,
    operation_duration,
)
from src.production import facade as production
from src.sales.models import CalcOperation, CalcOperationDependency

Centers = Mapping[UUID, production.WorkCenterBrief]


def is_supply(operation: CalcOperation, centers: Centers) -> bool:
    center = centers.get(operation.work_center_id)
    return bool(center and center.is_supply)


def duration_of(operation: CalcOperation, centers: Centers) -> int:
    return operation_duration(
        operation.hours, operation.people, is_supply=is_supply(operation, centers)
    )


def finish_of(operation: CalcOperation, centers: Centers) -> date | None:
    if operation.planned_start is None:
        return None
    return finish_date(operation.planned_start, duration_of(operation, centers))


def network(
    operations: Iterable[CalcOperation],
    dependencies: Iterable[CalcOperationDependency],
    centers: Centers,
) -> tuple[list[ScheduleNode], list[ScheduleEdge]]:
    nodes = [
        ScheduleNode(id=op.id, duration=duration_of(op, centers), not_before=op.not_before)
        for op in operations
    ]
    edges = [ScheduleEdge(dep.predecessor_id, dep.successor_id) for dep in dependencies]
    return nodes, edges


def centers_by_id() -> dict[UUID, production.WorkCenterBrief]:
    return {center.id: center for center in production.list_work_centers()}
