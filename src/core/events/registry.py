"""Реестр обработчиков событий, наполняемый из `handlers.py` модулей при старте приложения.

Ядру запрещено импортировать функциональные модули (инвариант И1), поэтому обработчики
регистрируют себя сами: `EventsConfig.ready()` вызывает `autodiscover_modules("handlers")`
(см. `django.contrib.admin.autodiscover`), который динамически импортирует `handlers.py`
каждого приложения из `INSTALLED_APPS`. Такой импорт не виден статическому анализатору
`import-linter`, поэтому граница между ядром и функциональными модулями не нарушается.

    # src/contracts/handlers.py
    from src.core.events.registry import subscribe

    @subscribe("contract.signed")
    def уведомить_финансы(event: OutboxEvent) -> None: ...
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.events.models import OutboxEvent

EventHandler = Callable[["OutboxEvent"], None]

_handlers: dict[str, list[EventHandler]] = defaultdict(list)


def subscribe(event_type: str) -> Callable[[EventHandler], EventHandler]:
    def decorator(handler: EventHandler) -> EventHandler:
        _handlers[event_type].append(handler)
        return handler

    return decorator


def get_handlers(event_type: str) -> list[EventHandler]:
    return list(_handlers.get(event_type, []))


def handler_name(handler: EventHandler) -> str:
    return f"{handler.__module__}.{handler.__qualname__}"


def clear() -> None:
    """Только для тестов: сбрасывает реестр между прогонами."""
    _handlers.clear()
