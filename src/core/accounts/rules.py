"""Предикаты прав доступа модуля «Ядро: учётные записи» (django-rules).

`in_same_department_or_below` и `is_department_head` знают о подразделениях через
`core.org.facade` — `core.accounts` лежит выше `core.org` в слоевом контракте
(`.importlinter`), импорт разрешён в эту сторону.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import rules

from src.core.accounts.groups import (
    ADMINISTRATOR,
    ESTIMATOR,
    FOREMAN,
    POWER_ENGINEER,
    PROCUREMENT_OFFICER,
    PRODUCTION_HEAD,
    PROJECT_MANAGER,
    QC_ENGINEER,
    TECHNOLOGIST,
    WAREHOUSE_HEAD,
)
from src.core.accounts.models import User
from src.core.org import facade as org


class _HasDepartment(Protocol):
    department_id: UUID


@rules.predicate
def is_administrator(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=ADMINISTRATOR).exists()


@rules.predicate
def is_department_head(user: User, department_id: UUID | None = None) -> bool:
    headed = org.list_departments_headed_by(user.id)
    if department_id is None:
        return bool(headed)
    return department_id in headed


@rules.predicate
def in_same_department_or_below(user: User, obj: _HasDepartment | None = None) -> bool:
    if obj is None or getattr(obj, "department_id", None) is None:
        return False

    headed = org.list_departments_headed_by(user.id)
    if not headed:
        return False

    allowed_ids: set[UUID] = set()
    for department_id in headed:
        allowed_ids.update(org.list_department_and_descendant_ids(department_id))

    return obj.department_id in allowed_ids


@rules.predicate
def is_project_manager(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=PROJECT_MANAGER).exists()


@rules.predicate
def is_estimator(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=ESTIMATOR).exists()


@rules.predicate
def is_technologist(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=TECHNOLOGIST).exists()


@rules.predicate
def is_procurement_officer(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=PROCUREMENT_OFFICER).exists()


@rules.predicate
def is_production_head(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=PRODUCTION_HEAD).exists()


@rules.predicate
def is_warehouse_head(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=WAREHOUSE_HEAD).exists()


@rules.predicate
def is_foreman(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=FOREMAN).exists()


@rules.predicate
def is_qc_engineer(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=QC_ENGINEER).exists()


@rules.predicate
def is_power_engineer(user: User, obj: Any = None) -> bool:
    return user.is_superuser or user.groups.filter(name=POWER_ENGINEER).exists()


@rules.predicate
def is_own_record(user: User, obj: Any = None) -> bool:
    if obj is None:
        return False
    if obj == user:
        return True
    return getattr(obj, "user_id", None) == user.id
