"""Единственный тестовый пример `DomainEvent` в этом модуле.

Используется только для проверки механизма publish/registry/dispatcher. Не является
реальным доменным событием — прикладные модули заводят собственные события в своих
`events.py` (см. docs/events.md).
"""

from __future__ import annotations

import dataclasses
from typing import ClassVar

from src.core.events.base import DomainEvent


@dataclasses.dataclass(frozen=True)
class WidgetTouched(DomainEvent):
    event_type: ClassVar[str] = "core_events.example.widget_touched"
    version: ClassVar[int] = 1

    note: str = ""
