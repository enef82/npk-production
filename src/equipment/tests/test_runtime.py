"""Ввод наработки за смену (`record_runtime`)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone

from src.equipment.exceptions import DayOverflow, FutureDate, InvalidHours, ReasonRequired
from src.equipment.models import RuntimeLog
from src.equipment.services.runtime import RuntimeDTO, record_runtime
from src.equipment.tests.factories import EquipmentFactory, IdleReasonFactory

pytestmark = pytest.mark.django_db


def _yesterday() -> date:
    return timezone.localdate() - timedelta(days=1)


def test_смена_записывается_и_повторный_ввод_заменяет_сутки() -> None:
    equipment = EquipmentFactory.create()
    reason = IdleReasonFactory.create()
    day = _yesterday()

    record_runtime(
        equipment.id,
        RuntimeDTO(date=day, run=Decimal("6"), idle=Decimal("2"), idle_reason_id=reason.id),
        actor_id=uuid4(),
    )
    record_runtime(
        equipment.id, RuntimeDTO(date=day, run=Decimal("7.5"), setup=Decimal("0.5")), actor_id=None
    )

    log = RuntimeLog.objects.get(equipment=equipment, date=day)
    assert (log.run, log.setup, log.idle) == (Decimal("7.50"), Decimal("0.50"), Decimal("0.00"))
    assert log.idle_reason is None


def test_больше_24_часов_в_сутки_не_принимается() -> None:
    equipment = EquipmentFactory.create()
    with pytest.raises(DayOverflow):
        record_runtime(
            equipment.id,
            RuntimeDTO(date=_yesterday(), run=Decimal("20"), down=Decimal("5")),
            actor_id=None,
        )


def test_простой_без_причины_не_принимается() -> None:
    equipment = EquipmentFactory.create()
    with pytest.raises(ReasonRequired):
        record_runtime(
            equipment.id, RuntimeDTO(date=_yesterday(), idle=Decimal("1")), actor_id=None
        )


def test_отрицательные_часы_не_принимаются() -> None:
    equipment = EquipmentFactory.create()
    with pytest.raises(InvalidHours):
        record_runtime(
            equipment.id, RuntimeDTO(date=_yesterday(), run=Decimal("-1")), actor_id=None
        )


def test_наработку_за_завтра_внести_нельзя() -> None:
    equipment = EquipmentFactory.create()
    with pytest.raises(FutureDate):
        record_runtime(
            equipment.id,
            RuntimeDTO(date=timezone.localdate() + timedelta(days=1), run=Decimal("1")),
            actor_id=None,
        )
