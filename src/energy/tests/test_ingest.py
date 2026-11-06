"""Приём интервалов от SCADA: построчная проверка, перезапись, идемпотентность по
`message_id` (повторная доставка неизбежна — CLAUDE.md §8)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from django.utils import timezone

from src.energy.exceptions import UnsupportedSchemaVersion
from src.energy.models import MeterInterval, ScadaMessage
from src.energy.services.ingest import ScadaEnvelope, ingest_intervals
from src.energy.tests.factories import MeterFactory, at

pytestmark = pytest.mark.django_db

YESTERDAY = timezone.localdate() - timedelta(days=1)


def _item(code: str, hour: int, minute: int, value: Any) -> dict[str, Any]:
    return {
        "type": "energy_interval",
        "meter_code": code,
        "start": at(YESTERDAY, hour, minute).isoformat(),
        "value": value,
    }


def _envelope(items: list[dict[str, Any]], message_id: str | None = None) -> ScadaEnvelope:
    return ScadaEnvelope(
        schema_version="1.0",
        source_id="scada-ceh-1",
        message_id=message_id or str(uuid4()),
        items=items,
    )


def test_пакет_принимается_и_плохие_строки_отклоняются_по_одной() -> None:
    meter = MeterFactory.create(code="СЧ-ЭЭ-ВВОД")
    items = [
        _item("СЧ-ЭЭ-ВВОД", 10, 0, "12.5"),
        _item("СЧ-ЭЭ-ВВОД", 10, 30, "13.0001"),
        _item("НЕТ-ТАКОГО", 10, 0, "1"),
        _item("СЧ-ЭЭ-ВВОД", 10, 15, "1"),
        _item("СЧ-ЭЭ-ВВОД", 11, 0, 1.5),
        _item("СЧ-ЭЭ-ВВОД", 11, 30, "-1"),
        {"type": "equipment_state", "equipment_code": "ИН-0012", "state": "run"},
        {**_item("СЧ-ЭЭ-ВВОД", 12, 0, "1"), "start": "2026-11-05T12:00:00"},
    ]

    result = ingest_intervals(_envelope(items), actor_id=None)

    assert (result.accepted, result.rejected, result.duplicate) == (2, 6, False)
    assert [(e["index"], e["code"]) for e in result.errors] == [
        (2, "unknown_meter"),
        (3, "start_not_aligned"),
        (4, "invalid_value"),
        (5, "invalid_value"),
        (6, "unsupported_type"),
        (7, "invalid_start"),
    ]
    values = sorted(MeterInterval.objects.filter(meter=meter).values_list("value", flat=True))
    assert values == [Decimal("12.5000"), Decimal("13.0001")]


def test_повторная_доставка_пакета_ничего_не_меняет() -> None:
    meter = MeterFactory.create(code="СЧ-1")
    message_id = "msg-0001"
    first = ingest_intervals(_envelope([_item("СЧ-1", 9, 0, "5")], message_id), actor_id=None)

    again = ingest_intervals(
        _envelope([_item("СЧ-1", 9, 0, "999"), _item("СЧ-1", 9, 30, "1")], message_id),
        actor_id=None,
    )

    assert first.duplicate is False
    assert again.duplicate is True
    assert (again.accepted, again.rejected) == (1, 0)
    assert list(MeterInterval.objects.filter(meter=meter).values_list("value", flat=True)) == [
        Decimal("5.0000")
    ]
    assert ScadaMessage.objects.filter(message_id=message_id).count() == 1


def test_новый_пакет_перезаписывает_интервал_исправлением() -> None:
    meter = MeterFactory.create(code="СЧ-1")
    ingest_intervals(_envelope([_item("СЧ-1", 9, 0, "5")]), actor_id=None)
    ingest_intervals(_envelope([_item("СЧ-1", 9, 0, "6.25")]), actor_id=None)

    assert MeterInterval.objects.get(meter=meter).value == Decimal("6.2500")


def test_повтор_интервала_внутри_пакета_побеждает_последний() -> None:
    meter = MeterFactory.create(code="СЧ-1")
    result = ingest_intervals(
        _envelope([_item("СЧ-1", 9, 0, "1"), _item("СЧ-1", 9, 0, "2")]), actor_id=None
    )

    assert (result.accepted, result.rejected) == (1, 1)
    assert result.errors[0]["code"] == "duplicate_in_message"
    assert MeterInterval.objects.get(meter=meter).value == Decimal("2.0000")


def test_неподдерживаемая_версия_формата_отклоняет_пакет_целиком() -> None:
    MeterFactory.create(code="СЧ-1")
    envelope = ScadaEnvelope(
        schema_version="2.0", source_id="s", message_id="m", items=[_item("СЧ-1", 9, 0, "1")]
    )
    with pytest.raises(UnsupportedSchemaVersion):
        ingest_intervals(envelope, actor_id=None)
    assert not ScadaMessage.objects.exists()
