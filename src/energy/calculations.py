"""Чистые расчёты модуля «Энергоучёт» — без БД (CLAUDE.md §5): границы суток,
получасовые интервалы, раскладка расхода, тариф на дату, баланс узла."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.utils import timezone

HALF_HOUR = timedelta(minutes=30)
SLOTS_PER_DAY = 48
QUANT = Decimal("0.0001")
ZERO = Decimal("0")


def q4(value: Decimal) -> Decimal:
    return value.quantize(QUANT, rounding=ROUND_HALF_UP)


def day_start(day: date) -> datetime:
    """Начало суток в часовом поясе проекта — сутки отчётов локальные."""

    return timezone.make_aware(datetime.combine(day, time.min))


def is_half_hour(moment: datetime) -> bool:
    return moment.second == 0 and moment.microsecond == 0 and moment.minute in (0, 30)


def slot_of(moment: datetime) -> int:
    """Номер получаса в локальных сутках (0…47)."""

    local = timezone.localtime(moment)
    return local.hour * 2 + (1 if local.minute >= 30 else 0)


def spread(total: Decimal, slots: int) -> list[Decimal]:
    """Расход между показаниями — поровну по получасам; остаток округления — в последний
    интервал, чтобы сумма совпала с разностью показаний до последнего знака."""

    if slots <= 0:
        return []
    part = (total / slots).quantize(QUANT, rounding=ROUND_DOWN)
    values = [part] * slots
    values[-1] = total - part * (slots - 1)
    return values


@dataclass(frozen=True)
class TariffTable:
    """Периоды тарифа одного ресурса (по возрастанию начала) и запасной тариф."""

    starts: list[date]
    tariffs: list[Decimal]
    fallback: Decimal

    def on(self, day: date) -> Decimal:
        index = bisect.bisect_right(self.starts, day) - 1
        return self.tariffs[index] if index >= 0 else self.fallback


@dataclass(frozen=True)
class Balance:
    """Баланс узла: ввод − Σ дочерних = потери (небаланс)."""

    input: Decimal
    children: Decimal
    loss: Decimal
    loss_pct: Decimal | None


def balance(input_value: Decimal, children_value: Decimal) -> Balance:
    loss = input_value - children_value
    pct = (
        (loss / input_value * 100).quantize(Decimal("0.01"), ROUND_HALF_UP) if input_value else None
    )
    return Balance(input_value, children_value, loss, pct)


def specific_consumption(energy: Decimal, machine_hours: Decimal) -> Decimal | None:
    """Удельный расход, единиц ресурса на машино-час; без наработки — не определён."""

    if machine_hours <= 0:
        return None
    return (energy / machine_hours).quantize(Decimal("0.01"), ROUND_HALF_UP)
