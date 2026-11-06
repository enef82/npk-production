from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from src.energy.models import (
    EnergyResource,
    Meter,
    MeterInterval,
    MeterKind,
    MeterReading,
    MeterSource,
    TariffPeriod,
)


class EnergyResourceFactory(factory.django.DjangoModelFactory[EnergyResource]):
    """Ресурсы засевает миграция, `flush()` transactional-тестов их стирает — фабрика
    достаёт существующий по коду или заводит его."""

    class Meta:
        model = EnergyResource
        django_get_or_create = ("code",)

    code = "el"
    name = "Электроэнергия"
    unit = "кВт·ч"
    tariff = Decimal("0")


class TariffPeriodFactory(factory.django.DjangoModelFactory[TariffPeriod]):
    class Meta:
        model = TariffPeriod

    resource = factory.SubFactory(EnergyResourceFactory)
    valid_from = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=365))
    tariff = Decimal("7.9")


class MeterFactory(factory.django.DjangoModelFactory[Meter]):
    class Meta:
        model = Meter

    code = factory.Sequence(lambda n: f"СЧ-Т{n:04d}")
    name = factory.Sequence(lambda n: f"Счётчик {n}")
    resource = factory.SubFactory(EnergyResourceFactory)
    kind = MeterKind.INPUT
    source = MeterSource.SCADA


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class MeterIntervalFactory(factory.django.DjangoModelFactory[MeterInterval]):
    class Meta:
        model = MeterInterval

    meter = factory.SubFactory(MeterFactory)
    start = factory.LazyFunction(lambda: at(timezone.localdate() - timedelta(days=1), 10))
    value = Decimal("10")


class MeterReadingFactory(factory.django.DjangoModelFactory[MeterReading]):
    class Meta:
        model = MeterReading

    meter = factory.SubFactory(MeterFactory)
    taken_at = factory.LazyFunction(lambda: at(timezone.localdate() - timedelta(days=1), 0))
    value = Decimal("100")
