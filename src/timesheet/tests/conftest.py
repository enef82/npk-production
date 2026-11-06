"""Фикстуры тестов модуля «Табель»."""

from __future__ import annotations

import pytest

from src.timesheet.models import TimeCode
from src.timesheet.tests.reference_data import TIME_CODES


def ensure_time_codes() -> None:
    """Коды засевает миграция, но `flush()` любого транзакционного теста на `--reuse-db`
    стирает их без возврата (тот же класс дефекта, что `conftest.ensure_core_reference_data`
    в корне). Идемпотентно."""

    for order, (code, name, is_work, is_allocatable, multiplier) in enumerate(TIME_CODES):
        TimeCode.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "is_work": is_work,
                "is_allocatable": is_allocatable,
                "cost_multiplier": multiplier,
                "sort_order": (order + 1) * 10,
            },
        )


@pytest.fixture(autouse=True)
def _time_codes(request: pytest.FixtureRequest) -> None:
    marker = request.node.get_closest_marker("django_db")
    if marker is None and "db" not in request.fixturenames:
        return
    request.getfixturevalue("db")
    ensure_time_codes()
