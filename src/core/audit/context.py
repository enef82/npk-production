"""Прокидывание актора (кто вызвал сервис) в историю pghistory.

`pghistory.context()` — стек: вложенный вызов добавляет метаданные в уже открытый
контекст (например, открытый `HistoryMiddleware` для HTTP-запроса), а если контекста
ещё нет — открывает новый сам. Поэтому оборачивание сервисной функции в
`actor_context(actor_id)` одинаково работает и внутри HTTP-запроса (актор дополняет
`user`/`url` из middleware), и вне его — из Celery-задачи или management-команды,
где никакого запроса нет и `HistoryMiddleware` никогда не сработает.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pghistory


def actor_context(actor_id: UUID, **extra: Any) -> pghistory.context:
    """`**extra` — дополнительные метаданные записи истории, не хранящиеся как поле
    модели (например, причина архивации: `archive_party(..., reason=...)`)."""

    return pghistory.context(actor_id=str(actor_id), **extra)
