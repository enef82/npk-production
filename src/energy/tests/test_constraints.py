"""Ограничения БД модуля «Энергоучёт»: попытка нарушить → `IntegrityError`."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from src.energy.models import Meter
from src.energy.tests.factories import (
    MeterFactory,
    MeterIntervalFactory,
    MeterReadingFactory,
    TariffPeriodFactory,
    at,
)

pytestmark = pytest.mark.django_db

YESTERDAY = timezone.localdate() - timedelta(days=1)


def test_начало_интервала_не_кратное_30_минутам_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="energy_interval_start_half_hour"):
        MeterIntervalFactory.create(start=at(YESTERDAY, 10, 15))


def test_начало_интервала_с_секундами_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="energy_interval_start_half_hour"):
        MeterIntervalFactory.create(start=at(YESTERDAY, 10, 30) + timedelta(seconds=1))


def test_интервалы_на_00_и_30_минут_допустимы() -> None:
    meter = MeterFactory.create()
    MeterIntervalFactory.create(meter=meter, start=at(YESTERDAY, 0, 0))
    MeterIntervalFactory.create(meter=meter, start=at(YESTERDAY, 23, 30))
    assert meter.intervals.count() == 2


def test_второй_интервал_с_тем_же_началом_нарушает_constraint() -> None:
    interval = MeterIntervalFactory.create()
    with pytest.raises(IntegrityError, match="energy_interval_unique_start"):
        MeterIntervalFactory.create(meter=interval.meter, start=interval.start)


def test_отрицательный_расход_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="energy_interval_value_non_negative"):
        MeterIntervalFactory.create(value=Decimal("-0.1"))


def test_два_показания_на_одно_время_невозможны() -> None:
    reading = MeterReadingFactory.create()
    with pytest.raises(IntegrityError, match="energy_reading_unique_time"):
        MeterReadingFactory.create(meter=reading.meter, taken_at=reading.taken_at)


def test_счётчик_не_может_быть_родителем_самому_себе() -> None:
    meter = MeterFactory.create()
    with pytest.raises(IntegrityError, match="energy_meter_not_own_parent"):
        Meter.objects.filter(id=meter.id).update(parent=meter)


def test_код_счётчика_уникален() -> None:
    MeterFactory.create(code="СЧ-1")
    with pytest.raises(IntegrityError):
        MeterFactory.create(code="СЧ-1")


def test_два_тарифа_с_одной_даты_невозможны() -> None:
    period = TariffPeriodFactory.create()
    with pytest.raises(IntegrityError, match="energy_tariff_unique_start"):
        TariffPeriodFactory.create(resource=period.resource, valid_from=period.valid_from)


def test_отрицательный_тариф_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="energy_tariff_period_non_negative"):
        TariffPeriodFactory.create(tariff=Decimal("-1"))
