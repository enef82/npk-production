"""Предикаты прав доступа модуля «Оборудование и ТО» (django-rules).

Чтение — любой аутентифицированный (спецификация §4). Действия — по Django-правам,
выданным ролям через `core.accounts.groups.SEED_GROUP_PERMISSIONS`:
`equipment.manage_equipment` — начальник производства (всё, включая карточки, виды ТО,
справочники); `equipment.log_runtime` — мастер участка (смена, отказ, ремонт).
Право вести оборудование включает право вносить наработку.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import rules

__all__ = ["can_log_runtime", "can_manage_equipment"]


class _User(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


@rules.predicate
def can_manage_equipment(user: _User) -> bool:
    return user.is_superuser or user.has_perm("equipment.manage_equipment")


@rules.predicate
def can_log_runtime(user: _User) -> bool:
    return bool(can_manage_equipment(user)) or user.has_perm("equipment.log_runtime")
