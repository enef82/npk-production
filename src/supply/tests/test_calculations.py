"""Опоздание строки (`prLate` прототипа) и количество расходников на заказ (`toolLines`)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.supply.calculations import late_days, tool_quantity
from src.supply.models import LineCategory, LineStatus

TODAY = date(2026, 11, 6)
NEED = date(2026, 11, 10)


@pytest.mark.parametrize("status", [LineStatus.RECEIVED, LineStatus.RESERVED, LineStatus.ISSUED])
def test_строка_на_складе_или_в_цехе_не_опаздывает(status: LineStatus) -> None:
    assert late_days(status, date(2026, 11, 1), date(2026, 12, 1), TODAY) == 0


def test_поставка_позже_потребности_опаздывает_на_разницу() -> None:
    assert late_days(LineStatus.ORDERED, NEED, date(2026, 11, 15), TODAY) == 5
    assert late_days(LineStatus.ORDERED, NEED, date(2026, 11, 9), TODAY) == 0


def test_просроченный_срок_поставки_считается_от_сегодня() -> None:
    assert late_days(LineStatus.ORDERED, date(2026, 11, 2), date(2026, 11, 3), TODAY) == 4


def test_без_срока_опаздывает_только_просроченная_потребность() -> None:
    assert late_days(LineStatus.SENT, date(2026, 11, 3), None, TODAY) == 3
    assert late_days(LineStatus.DRAFT, NEED, None, TODAY) == 0


@pytest.mark.parametrize(
    ("order_qty", "expected"),
    [("1", "4"), ("5", "4"), ("6", "8"), ("12", "12")],
)
def test_расходники_на_каждые_пять_изделий(order_qty: str, expected: str) -> None:
    assert tool_quantity(LineCategory.CONSUMABLE, Decimal("4"), Decimal(order_qty)) == Decimal(
        expected
    )


@pytest.mark.parametrize("category", [LineCategory.TOOL, LineCategory.FIXTURE])
def test_инструмент_и_оснастка_на_заказ(category: LineCategory) -> None:
    assert tool_quantity(category, Decimal("2"), Decimal("40")) == Decimal("2")
