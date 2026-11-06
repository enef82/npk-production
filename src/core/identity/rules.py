"""Предикаты прав доступа модуля «Ядро: идентичность» (django-rules).

`core.identity` лежит ниже `core.accounts` в слоевом контракте (`.importlinter`,
`core-layers`) — импортировать роли/группы из `core.accounts` отсюда нельзя. Права
поэтому не через имена групп, а через стандартные Django-права модели: `add_party`
(автосоздаётся Django для любой модели) и `force_create_party` (объявлено в
`Party.Meta.permissions`). Какой группе какие права выданы — конфигурация
(Django admin/сид в `core.accounts`), а не импорт кода.
"""

from __future__ import annotations

from typing import Protocol

import rules


class _PermissionCheckable(Protocol):
    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


@rules.predicate
def can_create_party(user: _PermissionCheckable) -> bool:
    return user.has_perm("core_identity.add_party")


@rules.predicate
def can_force_create_party(user: _PermissionCheckable) -> bool:
    return user.has_perm("core_identity.force_create_party")
