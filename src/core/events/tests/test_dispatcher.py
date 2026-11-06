from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.events import registry
from src.core.events.dispatcher import dispatch_pending_events
from src.core.events.models import OutboxEvent, ProcessedEvent
from src.core.events.publisher import publish
from src.core.events.selectors import iter_stuck_events
from src.core.events.tests.support import WidgetTouched


@pytest.mark.django_db
def test_диспетчер_вызывает_всех_подписчиков() -> None:
    called: list[str] = []

    @registry.subscribe(WidgetTouched.event_type)
    def первый(event: OutboxEvent) -> None:
        called.append("первый")

    @registry.subscribe(WidgetTouched.event_type)
    def второй(event: OutboxEvent) -> None:
        called.append("второй")

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    processed = dispatch_pending_events()

    assert processed == 1
    assert set(called) == {"первый", "второй"}
    event = OutboxEvent.objects.get()
    assert event.processed_at is not None
    assert ProcessedEvent.objects.filter(event=event).count() == 2


@pytest.mark.django_db
def test_повторная_обработка_идемпотентна() -> None:
    calls = {"count": 0}

    @registry.subscribe(WidgetTouched.event_type)
    def handler(event: OutboxEvent) -> None:
        calls["count"] += 1

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    dispatch_pending_events()
    dispatch_pending_events()

    assert calls["count"] == 1


@pytest.mark.django_db
def test_падение_одного_обработчика_не_мешает_остальным() -> None:
    calls: list[str] = []

    @registry.subscribe(WidgetTouched.event_type)
    def падающий(event: OutboxEvent) -> None:
        raise ValueError("сбой обработчика")

    @registry.subscribe(WidgetTouched.event_type)
    def успешный(event: OutboxEvent) -> None:
        calls.append("успешный")

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    dispatch_pending_events()

    assert calls == ["успешный"]
    event = OutboxEvent.objects.get()
    assert event.processed_at is None
    assert event.attempts == 1
    assert "сбой обработчика" in event.last_error
    assert ProcessedEvent.objects.filter(event=event).count() == 1
    assert ProcessedEvent.objects.filter(event=event, handler_name__contains="успешный").exists()


@pytest.mark.django_db
def test_упавшее_событие_повторяется_и_считает_попытки() -> None:
    state = {"fail": True}
    calls = {"count": 0}

    @registry.subscribe(WidgetTouched.event_type)
    def handler(event: OutboxEvent) -> None:
        calls["count"] += 1
        if state["fail"]:
            raise ValueError("временный сбой")

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    dispatch_pending_events()
    event = OutboxEvent.objects.get()
    assert event.attempts == 1
    assert event.processed_at is None
    assert event.next_attempt_at is not None

    # Обработчик "чинится", а задержка повторной попытки — истекла.
    state["fail"] = False
    OutboxEvent.objects.filter(id=event.id).update(next_attempt_at=timezone.now())

    dispatch_pending_events()

    event.refresh_from_db()
    assert calls["count"] == 2
    assert event.attempts == 1
    assert event.processed_at is not None


@pytest.mark.django_db
def test_событие_после_N_неудач_помечается_требующим_внимания(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from django.conf import settings

    monkeypatch.setattr(settings, "EVENTS_MAX_ATTEMPTS", 2)
    calls = {"count": 0}

    @registry.subscribe(WidgetTouched.event_type)
    def всегда_падающий(event: OutboxEvent) -> None:
        calls["count"] += 1
        raise ValueError("постоянный сбой")

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    dispatch_pending_events()
    OutboxEvent.objects.update(next_attempt_at=timezone.now())
    dispatch_pending_events()

    event = OutboxEvent.objects.get()
    assert event.attempts == 2
    assert list(iter_stuck_events()) == [event]

    # Лимит исчерпан — диспетчер больше не подхватывает событие автоматически.
    OutboxEvent.objects.update(next_attempt_at=timezone.now())
    processed = dispatch_pending_events()

    assert processed == 0
    assert calls["count"] == 2


@pytest.mark.django_db
def test_диспетчер_не_теряет_события_при_перезапуске_воркера() -> None:
    """Состояние живёт в БД: повторный вызов dispatch_pending_events эквивалентен

    перезапуску воркера — ни один Celery-процесс не хранит очередь в памяти.
    """

    state = {"fail": True}

    @registry.subscribe(WidgetTouched.event_type)
    def handler(event: OutboxEvent) -> None:
        if state["fail"]:
            raise ValueError("воркер упал посреди обработки")

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=uuid4()))

    # "Воркер" падает на первой попытке.
    dispatch_pending_events()
    event = OutboxEvent.objects.get()
    assert event.processed_at is None
    assert event.attempts == 1

    # "Перезапуск воркера" — просто новый вызов той же функции с восстановленным обработчиком.
    state["fail"] = False
    OutboxEvent.objects.update(next_attempt_at=timezone.now())
    dispatch_pending_events()

    event.refresh_from_db()
    assert event.processed_at is not None
