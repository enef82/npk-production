"""Демо-данные «Энергоучёта»: 20 счётчиков прототипа, получасовые профили за 30 суток."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.energy import facade, selectors
from src.energy.models import Meter, MeterInterval, MeterReading
from src.equipment import facade as equipment

pytestmark = pytest.mark.django_db


def test_демо_заводит_счётчики_и_профили_идемпотентно() -> None:
    equipment.seed_demo()
    facade.seed_demo()
    facade.seed_demo()

    assert Meter.objects.count() == 20
    assert MeterInterval.objects.count() == 20 * 30 * 48
    assert MeterReading.objects.filter(meter__code="СЧ-ВОДА").count() == 31
    yesterday = timezone.localdate() - timedelta(days=1)
    el = selectors.get_resource_by_code("el")
    assert el is not None
    rows = selectors.meter_tree(el, yesterday - timedelta(days=27), yesterday)
    root = rows[0]
    assert root.meter.code == "СЧ-ЭЭ-ВВОД"
    # Ввод больше суммы дочерних — потери 1–2,5 % плюс аномалия.
    assert root.balance is not None
    assert root.balance.loss > 0
    laser = next(
        r
        for r in selectors.specific_consumption_report(yesterday - timedelta(days=27), yesterday)
        if r.meter.code == "СЧ-ЭЭ-ЛАЗ"
    )
    assert laser.specific is not None
    assert laser.machine_hours > 0
