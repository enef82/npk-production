"""Предикаты прав доступа модуля «Производство» (django-rules,
`docs/spec/00-prilozhenie-proizvodstvo.md` §4).

Чтение всех экранов — любой аутентифицированный. Действия — по Django-правам
(`can_*` спрашивают `has_perm`, права выданы ролям картой
`core.accounts.groups.SEED_GROUP_PERMISSIONS`) плюс объектные отношения: ответственный за
операцию, ответственный за этап, менеджер заказа. Ответственный — сотрудник, а не роль:
пользователь без сотрудника ответственным быть не может.

Сотрудник пользователя запоминается на объекте пользователя на время запроса: доска
проверяет способности по каждой карточке, и без этого каждый предикат ходил бы в БД.
"""

from __future__ import annotations

from uuid import UUID

import rules

from src.core.accounts.models import User
from src.core.org import facade as org
from src.production.models import Operation, OrderStageApproval, ProductionOrder

_CACHE_ATTR = "_production_employee_id"
_MISSING = object()


def employee_id_of(user: User) -> UUID | None:
    cached = getattr(user, _CACHE_ATTR, _MISSING)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]
    employee = org.get_employee_by_user(user.id)
    value = employee.id if employee is not None else None
    setattr(user, _CACHE_ATTR, value)
    return value


@rules.predicate
def can_manage_orders(user: User) -> bool:
    return user.has_perm("production.manage_orders")


@rules.predicate
def can_plan_operations(user: User) -> bool:
    return user.has_perm("production.plan_operations")


@rules.predicate
def can_approve_any(user: User) -> bool:
    return user.has_perm("production.approve_any")


@rules.predicate
def can_manage_reference(user: User) -> bool:
    return user.has_perm("production.manage_reference")


@rules.predicate
def can_manage_documents(user: User) -> bool:
    return user.has_perm("production.manage_documents") or user.has_perm("production.manage_orders")


@rules.predicate
def is_operation_responsible(user: User, operation: Operation | None = None) -> bool:
    if operation is None or operation.responsible_id is None:
        return False
    return employee_id_of(user) == operation.responsible_id


@rules.predicate
def is_stage_responsible(user: User, approval: OrderStageApproval | None = None) -> bool:
    if approval is None or approval.responsible_id is None:
        return False
    return employee_id_of(user) == approval.responsible_id


@rules.predicate
def is_order_manager(user: User, order: ProductionOrder | None = None) -> bool:
    if order is None:
        return False
    return employee_id_of(user) == order.manager_id


def can_work_on_operation(user: User, operation: Operation) -> bool:
    """Статус и прогресс операции — ответственный или тот, кто планирует операции."""

    return bool(is_operation_responsible(user, operation) or can_plan_operations(user))


def can_approve_operation(user: User, operation: Operation) -> bool:
    return bool(is_operation_responsible(user, operation) or can_approve_any(user))


def can_approve_stage(user: User, approval: OrderStageApproval) -> bool:
    return bool(is_stage_responsible(user, approval) or can_approve_any(user))


def can_move_order(user: User, order: ProductionOrder, current: OrderStageApproval | None) -> bool:
    """Перевести этап может начальник производства, ответственный за текущий этап и
    менеджер заказа; есть ли виза — проверяет сервис."""

    return bool(
        can_manage_orders(user)
        or is_order_manager(user, order)
        or (current is not None and is_stage_responsible(user, current))
    )
