"""Предикаты прав доступа модуля «Энергоучёт» (django-rules).

Чтение — любой аутентифицированный (спецификация §4). `energy.manage_meters` — роль
«энергетик» (счётчики, тарифы, ручные показания). `energy.ingest_intervals` — у
технического пользователя SCADA, выдаётся ему лично (не роли): сервисной учётной
записи не нужно ничего, кроме приёма интервалов.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import rules

__all__ = ["can_ingest_intervals", "can_manage_meters"]


class _User(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


@rules.predicate
def can_manage_meters(user: _User) -> bool:
    return user.is_superuser or user.has_perm("energy.manage_meters")


@rules.predicate
def can_ingest_intervals(user: _User) -> bool:
    return user.is_superuser or user.has_perm("energy.ingest_intervals")
