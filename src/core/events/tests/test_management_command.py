from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from src.core.events.tests.factories import OutboxEventFactory


@pytest.mark.django_db
def test_команда_показывает_застрявшие_события(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.conf import settings

    monkeypatch.setattr(settings, "EVENTS_MAX_ATTEMPTS", 3)
    застрявшее = OutboxEventFactory(attempts=3, last_error="постоянный сбой")
    OutboxEventFactory(attempts=1)  # ещё не исчерпало лимит — в вывод не попадает

    out = StringIO()
    call_command("stuck_events", stdout=out)

    вывод = out.getvalue()
    assert str(застрявшее.id) in вывод  # type: ignore[attr-defined]
    assert "постоянный сбой" in вывод
    assert вывод.count("core_events.example.widget_touched") == 1


@pytest.mark.django_db
def test_команда_без_застрявших_событий_печатает_сообщение() -> None:
    out = StringIO()
    call_command("stuck_events", stdout=out)

    assert "Застрявших событий нет." in out.getvalue()
