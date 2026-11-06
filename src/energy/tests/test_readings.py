"""Ручной ввод показаний: расход между показаниями — в получасовые интервалы,
сумма совпадает с разностью до последнего знака (Decimal)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone

from src.energy.exceptions import InvalidReading
from src.energy.models import MeterInterval, MeterSource
from src.energy.services.reading import record_reading
from src.energy.tests.factories import MeterFactory, at

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() - timedelta(days=2)


def test_первое_показание_только_точка_отсчёта() -> None:
    meter = MeterFactory.create(source=MeterSource.MANUAL)
    record_reading(meter.id, at(DAY, 0), Decimal("1000"), actor_id=None)
    assert not MeterInterval.objects.filter(meter=meter).exists()


def test_расход_между_показаниями_раскладывается_по_получасам_без_потерь() -> None:
    meter = MeterFactory.create(source=MeterSource.MANUAL)
    record_reading(meter.id, at(DAY, 0), Decimal("1000"), actor_id=None)

    record_reading(meter.id, at(DAY + timedelta(days=1), 0), Decimal("1010.0001"), actor_id=None)

    intervals = MeterInterval.objects.filter(meter=meter)
    assert intervals.count() == 48
    assert intervals.aggregate(total=Sum("value"))["total"] == Decimal("10.0001")
    assert set(intervals.values_list("source", flat=True)) == {MeterSource.MANUAL}
    assert intervals.order_by("start").first().value == Decimal("0.2083")  # type: ignore[union-attr]


def test_показание_раньше_последнего_не_принимается() -> None:
    meter = MeterFactory.create()
    record_reading(meter.id, at(DAY, 12), Decimal("10"), actor_id=None)
    with pytest.raises(InvalidReading, match="позже"):
        record_reading(meter.id, at(DAY, 6), Decimal("20"), actor_id=None)


def test_уменьшение_накопительного_показания_не_принимается() -> None:
    meter = MeterFactory.create()
    record_reading(meter.id, at(DAY, 0), Decimal("10"), actor_id=None)
    with pytest.raises(InvalidReading, match="меньше"):
        record_reading(meter.id, at(DAY, 6), Decimal("9"), actor_id=None)


def test_время_показания_должно_быть_кратно_30_минутам() -> None:
    meter = MeterFactory.create()
    with pytest.raises(InvalidReading, match="30 минутам"):
        record_reading(meter.id, at(DAY, 10, 10), Decimal("1"), actor_id=None)
