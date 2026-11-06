"""Сеть операций заказа для `core.common.scheduling`: узлы и связи из моделей.

Общая для сервисов (пересчёт `planned_start`) и селекторов (критический путь, Гант).
Без запросов к БД: на вход — уже загруженные операции с `work_center` и связи.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from django.utils import timezone

from src.core.common.scheduling import (
    ScheduleEdge,
    ScheduleNode,
    finish_date,
    operation_duration,
)
from src.production.models import Operation, OperationDependency, OperationStatus


def duration_of(operation: Operation) -> int:
    return operation_duration(
        operation.hours, operation.people, is_supply=operation.work_center.is_supply
    )


def finish_of(operation: Operation) -> date | None:
    if operation.planned_start is None:
        return None
    return finish_date(operation.planned_start, duration_of(operation))


def fixed_start_of(operation: Operation) -> date | None:
    """Начатая операция стоит по факту: её плановое начало не пересчитывается."""

    if operation.status == OperationStatus.WAIT:
        return None
    if operation.planned_start is not None:
        return operation.planned_start
    if operation.started_at is not None:
        return timezone.localtime(operation.started_at).date()
    return timezone.localdate()


def network(
    operations: Iterable[Operation], dependencies: Iterable[OperationDependency]
) -> tuple[list[ScheduleNode], list[ScheduleEdge]]:
    nodes = [
        ScheduleNode(
            id=op.id,
            duration=duration_of(op),
            fixed_start=fixed_start_of(op),
            not_before=op.not_before,
        )
        for op in operations
    ]
    edges = [ScheduleEdge(dep.predecessor_id, dep.successor_id) for dep in dependencies]
    return nodes, edges
