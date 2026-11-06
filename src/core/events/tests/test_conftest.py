"""Регрессия на баг, найденный на шаге 11: `_clean_registry` (autouse, `conftest.py`)
раньше просто вызывал `registry.clear()` до и после каждого теста — это стирало не
только тестовые подписки, но и обработчики, зарегистрированные один раз при старте
приложения (`autodiscover_modules("handlers")`, `EventsConfig.ready()`). До появления
`procurement.handlers.block_vendor_on_party_archived` в системе не было ни одного
постоянного обработчика, поэтому дефект был невидим — не хватило внимательности,
чтобы предсказать его заранее, зато хватит теста, чтобы не потерять снова."""

from __future__ import annotations

from src.core.events import registry
from src.core.events.models import OutboxEvent
from src.core.events.tests.conftest import restore_handlers, snapshot_handlers


def test_restore_handlers_сохраняет_обработчик_зарегистрированный_до_снимка() -> None:
    @registry.subscribe("permanent.event_for_test")
    def permanent(event: OutboxEvent) -> None:
        pass

    snapshot = snapshot_handlers()

    # Симулирует то, что делает `_clean_registry` внутри теста: очистка + подписки,
    # характерные для конкретного теста, которых не должно быть в снимке "до".
    registry.clear()
    assert registry.get_handlers("permanent.event_for_test") == []

    @registry.subscribe("permanent.event_for_test")
    def temporary(event: OutboxEvent) -> None:
        pass

    restore_handlers(snapshot)

    assert registry.get_handlers("permanent.event_for_test") == [permanent]


def test_restore_handlers_не_добавляет_события_отсутствовавшие_в_снимке() -> None:
    snapshot = snapshot_handlers()
    assert "another.event_for_test" not in snapshot

    @registry.subscribe("another.event_for_test")
    def temporary(event: OutboxEvent) -> None:
        pass

    restore_handlers(snapshot)

    assert registry.get_handlers("another.event_for_test") == []
