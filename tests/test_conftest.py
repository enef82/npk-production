"""Регрессия на `ensure_core_reference_data` (корневой `conftest.py`): обязана
восстанавливать посеянные RunPython-миграцией данные, если их стёрли, а не только
существовать «для галочки» — тот же приём, что `src/core/events/tests/test_conftest.py`."""

from __future__ import annotations

import pytest

from conftest import ensure_core_reference_data
from src.core.numbering.models import Numerator
from src.core.org.models import Position
from tests.reference_data import CORE_NUMERATORS, CORE_TRADE_POSITIONS


@pytest.mark.django_db
def test_ensure_core_reference_data_восстанавливает_стёртые_нумераторы() -> None:
    codes = [code for code, *_ in CORE_NUMERATORS]
    Numerator.objects.filter(code__in=codes).delete()

    ensure_core_reference_data()

    assert Numerator.objects.filter(code__in=codes).count() == len(codes)


@pytest.mark.django_db
def test_ensure_core_reference_data_восстанавливает_должности_рабочих() -> None:
    Position.objects.filter(name__in=[name for name, _ in CORE_TRADE_POSITIONS]).delete()

    ensure_core_reference_data()

    for name, category in CORE_TRADE_POSITIONS:
        assert Position.objects.filter(name=name, category=category).exists()


@pytest.mark.django_db
def test_ensure_core_reference_data_идемпотентна() -> None:
    ensure_core_reference_data()
    ensure_core_reference_data()

    for code, *_ in CORE_NUMERATORS:
        assert Numerator.objects.filter(code=code).count() == 1
