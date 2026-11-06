"""Отчёты «Энергоучёта» в Decimal: стоимость по тарифу на каждые сутки, баланс узла,
профиль суток, удельный расход на машино-час."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.energy import selectors
from src.energy.models import MeterKind
from src.energy.tests.factories import (
    EnergyResourceFactory,
    MeterFactory,
    MeterIntervalFactory,
    TariffPeriodFactory,
    at,
)
from src.equipment.tests.factories import EquipmentFactory, RuntimeLogFactory

pytestmark = pytest.mark.django_db

D1 = timezone.localdate() - timedelta(days=3)
D2 = D1 + timedelta(days=1)


def _value(meter: object, day: date, hour: int, value: str) -> None:
    MeterIntervalFactory.create(meter=meter, start=at(day, hour), value=Decimal(value))


def test_стоимость_считается_по_тарифу_каждых_суток() -> None:
    el = EnergyResourceFactory.create(tariff=Decimal("1"))
    TariffPeriodFactory.create(
        resource=el, valid_from=D1 - timedelta(days=100), tariff=Decimal("7.9")
    )
    TariffPeriodFactory.create(resource=el, valid_from=D2, tariff=Decimal("8.1"))
    root = MeterFactory.create(resource=el)
    child = MeterFactory.create(resource=el, parent=root, kind=MeterKind.NODE)
    _value(root, D1, 10, "100")
    _value(root, D2, 10, "50.5")
    _value(child, D1, 10, "999")  # дочерний не суммируется в расход ресурса

    daily = selectors.consumption(D1, D2, resource_id=el.id)
    monthly = selectors.consumption(D1, D2, resource_id=el.id, by_month=True)

    assert [(r.period, r.quantity, r.cost) for r in daily] == [
        (D1, Decimal("100.0000"), Decimal("790.0000")),
        (D2, Decimal("50.5000"), Decimal("409.0500")),
    ]
    assert sum(r.quantity for r in monthly) == Decimal("150.5000")
    assert sum(r.cost for r in monthly) == Decimal("1199.0500")


def test_тариф_до_первого_периода_берётся_из_ресурса() -> None:
    el = EnergyResourceFactory.create(tariff=Decimal("5"))
    el.tariff = Decimal("5")
    el.save()
    root = MeterFactory.create(resource=el)
    _value(root, D1, 10, "2")

    (row,) = selectors.consumption(D1, D1, resource_id=el.id)

    assert row.cost == Decimal("10.0000")


def test_баланс_узла_ввод_минус_сумма_дочерних() -> None:
    el = EnergyResourceFactory.create()
    root = MeterFactory.create(resource=el)
    a = MeterFactory.create(resource=el, parent=root, kind=MeterKind.SHOP)
    b = MeterFactory.create(resource=el, parent=root, kind=MeterKind.SHOP)
    _value(root, D1, 10, "100")
    _value(a, D1, 10, "60")
    _value(b, D1, 10, "35")
    _value(root, D2, 10, "40")
    _value(a, D2, 10, "40")

    result = selectors.node_balance(root, D1, D2)
    tree = {row.meter.id: row for row in selectors.meter_tree(el, D1, D2)}

    assert result.total.loss == Decimal("5.0000")
    assert result.total.loss_pct == Decimal("3.57")  # 5 / 140
    assert [d.balance.loss for d in result.days] == [Decimal("5.0000"), Decimal("0.0000")]
    root_balance = tree[root.id].balance
    assert root_balance is not None
    assert root_balance.loss == Decimal("5.0000")
    assert tree[a.id].level == 1
    assert tree[a.id].balance is None


def test_профиль_суток_48_получасов() -> None:
    meter = MeterFactory.create()
    MeterIntervalFactory.create(meter=meter, start=at(D1, 0, 0), value=Decimal("1.5"))
    MeterIntervalFactory.create(meter=meter, start=at(D1, 23, 30), value=Decimal("2"))
    MeterIntervalFactory.create(meter=meter, start=at(D2, 0, 0), value=Decimal("100"))

    profile = selectors.day_profile(meter.id, D1)

    assert len(profile) == 48
    assert profile[0] == Decimal("1.5000")
    assert profile[47] == Decimal("2.0000")
    assert sum(profile) == Decimal("3.5000")


def test_удельный_расход_на_машино_час_по_наработке_оборудования() -> None:
    el = EnergyResourceFactory.create()
    TariffPeriodFactory.create(
        resource=el, valid_from=D1 - timedelta(days=1), tariff=Decimal("7.9")
    )
    equipment = EquipmentFactory.create()
    RuntimeLogFactory.create(equipment=equipment, date=D1, run=Decimal("6"), setup=Decimal("1"))
    RuntimeLogFactory.create(equipment=equipment, date=D2, run=Decimal("5"), setup=Decimal("0"))
    meter = MeterFactory.create(resource=el, kind=MeterKind.EQUIPMENT, equipment_id=equipment.id)
    _value(meter, D1, 10, "200")
    _value(meter, D2, 10, "130")

    (row,) = selectors.specific_consumption_report(D1, D2)

    assert row.machine_hours == Decimal("12.00")
    assert row.energy == Decimal("330.0000")
    assert row.specific == Decimal("27.50")
    assert row.cost == Decimal("2607.0000")
    assert row.inventory_no == equipment.inventory_no
