"""Предикаты прав доступа модуля «Снабжение и склад» (django-rules,
`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4, §4; роли прототипа `ROLE_SNAB`,
`ROLE_STORE`).

Чтение — любой аутентифицированный. Черновики, передача в закупку и заявки «на склад /
ТО» — любой работающий в приложении: пользователь с сотрудником и хотя бы одним
прикладным правом (наблюдатель прав не имеет — только чтение). Заказ поставщику и срок
поставки — `supply.order_lines` (снабженец). Приёмка, резерв и выдача в цех —
`supply.store_lines` (начальник склада, начальник производства).
"""

from __future__ import annotations

from uuid import UUID

import rules

from src.core.accounts.models import User
from src.core.org import facade as org

__all__ = [
    "can_manage_reference",
    "can_order_lines",
    "can_request_lines",
    "can_store_lines",
    "employee_id_of",
]

_CACHE_ATTR = "_supply_employee_id"
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
def can_order_lines(user: User) -> bool:
    return user.is_superuser or user.has_perm("supply.order_lines")


@rules.predicate
def can_store_lines(user: User) -> bool:
    return user.is_superuser or user.has_perm("supply.store_lines")


@rules.predicate
def can_request_lines(user: User) -> bool:
    if user.is_superuser:
        return True
    return employee_id_of(user) is not None and bool(user.get_all_permissions())


@rules.predicate
def can_manage_reference(user: User) -> bool:
    """Поставщики и типовая оснастка — снабжение и склад."""

    return bool(can_order_lines(user) or can_store_lines(user))
