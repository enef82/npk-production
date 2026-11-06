"""Точка входа диспетчера outbox — для Celery-задачи (`tasks.py`) и management-команд.

Сама обработка события и все изменения состояния `OutboxEvent`/`ProcessedEvent`
находятся в `services/dispatch.py` (инвариант И3: транзакции открываются только
в services/, этот файл — тонкая оркестрация, как и `tasks.py`).
"""

from __future__ import annotations

from src.core.events.services.dispatch import dispatch_batch


def dispatch_pending_events(batch_size: int | None = None) -> int:
    return dispatch_batch(batch_size=batch_size)
