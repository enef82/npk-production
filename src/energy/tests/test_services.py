"""Счётчики (дерево без циклов, один ресурс) и тарифы (история, тариф на сегодня)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.energy.exceptions import InvalidParent, InvalidTariff, MeterCodeTaken
from src.energy.models import EnergyResource, MeterKind, TariffPeriod
from src.energy.services.meter import MeterDTO, create_meter, update_meter
from src.energy.services.resource import set_tariff
from src.energy.tests.factories import EnergyResourceFactory, MeterFactory

pytestmark = pytest.mark.django_db


def _dto(meter_code: str, resource: EnergyResource, parent_id: object = None) -> MeterDTO:
    return MeterDTO(
        code=meter_code,
        name=meter_code,
        resource_id=resource.id,
        kind=MeterKind.NODE,
        parent_id=parent_id,  # type: ignore[arg-type]
    )


def test_дерево_счётчиков_не_замыкается_в_цикл() -> None:
    el = EnergyResourceFactory.create()
    root = create_meter(_dto("ВВОД", el), actor_id=None)
    node = create_meter(_dto("УЗЕЛ", el, root.id), actor_id=None)
    leaf = create_meter(_dto("СТАНОК", el, node.id), actor_id=None)

    with pytest.raises(InvalidParent):
        update_meter(root.id, _dto("ВВОД", el, leaf.id), actor_id=None)


def test_родитель_другого_ресурса_не_принимается() -> None:
    gas = EnergyResourceFactory.create(code="gas", name="Газ", unit="м³")
    el_root = MeterFactory.create()
    with pytest.raises(InvalidParent):
        create_meter(_dto("ПЕЧЬ", gas, el_root.id), actor_id=None)


def test_повтор_кода_счётчика_это_конфликт() -> None:
    el = EnergyResourceFactory.create()
    create_meter(_dto("СЧ-1", el), actor_id=None)
    with pytest.raises(MeterCodeTaken):
        create_meter(_dto("СЧ-1", el), actor_id=None)


def test_тариф_ресурса_это_период_действующий_сегодня() -> None:
    resource = EnergyResourceFactory.create(tariff=Decimal("0"))
    today = timezone.localdate()

    set_tariff(resource.id, today - timedelta(days=30), Decimal("7.9"), actor_id=None)
    set_tariff(resource.id, today + timedelta(days=30), Decimal("8.5"), actor_id=None)

    resource.refresh_from_db()
    assert resource.tariff == Decimal("7.9000")
    assert TariffPeriod.objects.filter(resource=resource).count() == 2


def test_отрицательный_тариф_не_принимается() -> None:
    resource = EnergyResourceFactory.create()
    with pytest.raises(InvalidTariff):
        set_tariff(resource.id, timezone.localdate(), Decimal("-1"), actor_id=None)
