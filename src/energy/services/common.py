"""Общее для сервисов модуля «Энергоучёт»."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from uuid import UUID

from src.core.audit.context import actor_context


def as_actor(actor_id: UUID | None) -> AbstractContextManager[object]:
    """Контекст истории pghistory: с актором — для пользовательских действий, без —
    для сида демо-данных."""

    return actor_context(actor_id) if actor_id is not None else nullcontext()
