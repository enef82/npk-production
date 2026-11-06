"""Общие фикстуры тестов модуля «Ядро: события»."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.events import registry


def snapshot_handlers() -> dict[str, list[registry.EventHandler]]:
    return {event_type: list(handlers) for event_type, handlers in registry._handlers.items()}


def restore_handlers(snapshot: dict[str, list[registry.EventHandler]]) -> None:
    registry.clear()
    for event_type, handlers in snapshot.items():
        registry._handlers[event_type] = handlers


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Изолирует тестовые подписки (`WidgetTouched` и т.п.) друг от друга — но не
    просто `clear()` до и после: `_handlers` также хранит обработчики, зарегистрированные
    один раз при старте приложения через `autodiscover_modules("handlers")`
    (`EventsConfig.ready()`), например `procurement.handlers.block_vendor_on_party_archived`.
    Такие обработчики никогда не регистрируются заново — простой `clear()` без снимка
    состояния убивал бы их безвозвратно для всех тестов, идущих в сессии после этого
    модуля, а не только внутри него. Логика вынесена в `snapshot_handlers`/
    `restore_handlers` — не только ради фикстуры, но и чтобы её можно было проверить
    тестом напрямую (`test_conftest.py`), не полагаясь на то, что баг снова будет
    замечен только когда появится следующий постоянный обработчик."""

    snapshot = snapshot_handlers()
    registry.clear()
    yield
    restore_handlers(snapshot)
