"""Предикаты прав доступа модуля «ОТК и качество» (django-rules,
`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3, §4).

Чтение — любой аутентифицированный. Записать контроль — держатель
`quality.record_inspection` (инженер ОТК, мастер участка) или ответственный за операцию
(объектное отношение: сотрудник пользователя = ответственный). Справочники —
`quality.manage_reference` (инженер ОТК).
"""

from __future__ import annotations

from uuid import UUID

import rules

from src.core.accounts.models import User
from src.core.org import facade as org

__all__ = [
    "can_manage_reference",
    "can_record_for_operation",
    "can_record_inspection",
    "employee_id_of",
]

_CACHE_ATTR = "_quality_employee_id"
_MISSING = object()


def employee_id_of(user: User) -> UUID | None:
    """Сотрудник пользователя; запоминается на объекте пользователя на время запроса."""

    cached = getattr(user, _CACHE_ATTR, _MISSING)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]
    employee = org.get_employee_by_user(user.id)
    value = employee.id if employee is not None else None
    setattr(user, _CACHE_ATTR, value)
    return value


@rules.predicate
def can_record_inspection(user: User) -> bool:
    return user.is_superuser or user.has_perm("quality.record_inspection")


@rules.predicate
def can_manage_reference(user: User) -> bool:
    return user.is_superuser or user.has_perm("quality.manage_reference")


def can_record_for_operation(user: User, responsible_id: UUID | None) -> bool:
    if can_record_inspection(user):
        return True
    me = employee_id_of(user)
    return me is not None and me == responsible_id
