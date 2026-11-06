"""Базовый класс доменных событий, публикуемых через `core.events.publisher.publish`."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID


@dataclasses.dataclass(frozen=True)
class DomainEvent:
    """Базовый класс события. Наследник объявляет `event_type` и, если нужно, `version`.

    `aggregate_id` — идентификатор сущности, к которой относится событие; хранится
    в `OutboxEvent.aggregate_id` отдельной колонкой и не дублируется в `payload`.
    """

    event_type: ClassVar[str]
    version: ClassVar[int] = 1

    aggregate_id: UUID

    def to_payload(self) -> dict[str, Any]:
        return {
            field.name: _json_safe(getattr(self, field.name))
            for field in dataclasses.fields(self)
            if field.name != "aggregate_id"
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    return value
