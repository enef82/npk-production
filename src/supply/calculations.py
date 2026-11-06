"""Чистые расчёты снабжения без БД (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, Decimal

from src.supply.models.choices import CLOSED_STATUSES, LineCategory

_FIVE = Decimal(5)


def late_days(status: str, need_date: date, eta: date | None, today: date) -> int:
    """Опоздание строки к потребности, календарные дни (`prLate` прототипа): строка на
    складе или в цехе не опаздывает; со сроком поставки — от потребности до
    `max(срок, сегодня)`; без срока — сколько потребность уже просрочена."""

    if status in CLOSED_STATUSES:
        return 0
    if eta is not None:
        return max(0, (max(eta, today) - need_date).days)
    if need_date < today:
        return (today - need_date).days
    return 0


def tool_quantity(category: str, base: Decimal, order_quantity: Decimal) -> Decimal:
    """Расходники — на каждые пять изделий заказа (`toolLines`: × ceil(qty / 5)),
    инструмент и оснастка — на заказ."""

    if category != LineCategory.CONSUMABLE:
        return base
    batches = max(Decimal(1), (order_quantity / _FIVE).to_integral_value(ROUND_CEILING))
    return base * batches
