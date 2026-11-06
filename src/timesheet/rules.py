"""Предикаты прав доступа модуля «Табель» (django-rules).

Чтение — любой аутентифицированный (спецификация §4). Правка разноски и подача табеля:
`timesheet.edit_any` (начальник производства) — любое подразделение; руководитель
подразделения (`Department.head`) — своё и дочерние, без отдельного права: он отвечает
за то, что часы отработаны (прототип: подаёт руководитель); `timesheet.edit_department`
(мастер участка) — подразделение, где он сам числится. Согласование, возврат, передача
в 1С, закрытие и переоткрытие — `timesheet.approve_period` (экономист-сметчик). Визу по
своим заказам ставит сам менеджер — объектное отношение, а не роль (решается в API по
списку менеджеров с часами).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import rules

from src.core.org import facade as org

__all__ = [
    "can_approve_period",
    "can_edit_any",
    "can_edit_department",
    "current_employee_id",
    "is_department_head_of",
]


class _User(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


def current_employee_id(user: _User) -> UUID | None:
    employee = org.get_employee_by_user(user.id)
    return employee.id if employee is not None else None


@rules.predicate
def can_edit_any(user: _User) -> bool:
    return user.is_superuser or user.has_perm("timesheet.edit_any")


@rules.predicate
def is_department_head_of(user: _User, department_id: UUID | None = None) -> bool:
    if department_id is None:
        return False
    for headed in org.list_departments_headed_by(user.id):
        if department_id in org.list_department_and_descendant_ids(headed):
            return True
    return False


@rules.predicate
def can_edit_department(user: _User, department_id: UUID | None = None) -> bool:
    if department_id is None:
        return False
    if can_edit_any(user) or is_department_head_of(user, department_id):
        return True
    if not user.has_perm("timesheet.edit_department"):
        return False
    return org.get_department_id_for_user(user.id) == department_id


@rules.predicate
def can_approve_period(user: _User) -> bool:
    return user.is_superuser or user.has_perm("timesheet.approve_period")
