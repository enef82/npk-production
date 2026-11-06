"""Предикаты прав доступа модуля «Аналитика» (django-rules,
`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8, §4).

Отчёты читает любой аутентифицированный. Закрывает и переоткрывает отсечку недели
держатель `analytics.close_cutoff` — начальник производства.
"""

from __future__ import annotations

from uuid import UUID

import rules

from src.core.accounts.models import User
from src.core.org import facade as org

__all__ = ["can_close_cutoff", "employee_id_of"]


@rules.predicate
def can_close_cutoff(user: User) -> bool:
    return user.is_superuser or user.has_perm("analytics.close_cutoff")


def employee_id_of(user: User) -> UUID | None:
    employee = org.get_employee_by_user(user.id)
    return employee.id if employee is not None else None
