"""Итоги калькуляции заявки — чистые функции, как `calcTotals` прототипа
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2, «Итоги»). Образец — `crm/calculations.py`
ИС: ни одного обращения к БД, входы и выходы — датаклассы и `Decimal`.

Формулы: материалы = Σ кол × цена; труд = Σ н-ч × ставка участка (снабжение 0);
часы = Σ н-ч без снабжения; накладные = труд × накладные %; себестоимость = материалы +
труд + накладные; цена = себестоимость × (1 + наценка %); НДС = цена × НДС %;
итог = цена + НДС; прибыль = цена − себестоимость.

Проценты передаются **в процентах** (`Decimal("20")`, не `0.2`). Промежуточные величины
— полной точности `Decimal`; округление «половина вверх» до 4 знаков — один раз на
выходе каждой итоговой величины (хранится 4 знака, до копеек — только при выводе).
`float` на входе — `TypeError` (И6).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_HUNDRED = Decimal(100)
_STORE = Decimal("0.0001")


@dataclass(frozen=True)
class MaterialLine:
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True)
class LaborLine:
    hours: Decimal
    rate: Decimal
    is_supply: bool


@dataclass(frozen=True)
class CalcTotals:
    materials: Decimal
    labor: Decimal
    hours: Decimal
    overhead: Decimal
    cost: Decimal
    price: Decimal
    vat: Decimal
    total: Decimal
    profit: Decimal


def _decimal(value: object, what: str) -> Decimal:
    if isinstance(value, float) or not isinstance(value, Decimal):
        raise TypeError(f"{what}: ожидается Decimal, получено {type(value).__name__} (И6)")
    return value


def _store(value: Decimal) -> Decimal:
    return value.quantize(_STORE, ROUND_HALF_UP)


def calc_totals(
    materials: Iterable[MaterialLine],
    operations: Iterable[LaborLine],
    *,
    overhead_pct: Decimal,
    margin_pct: Decimal,
    vat_pct: Decimal,
) -> CalcTotals:
    overhead_pct = _decimal(overhead_pct, "Накладные")
    margin_pct = _decimal(margin_pct, "Наценка")
    vat_pct = _decimal(vat_pct, "НДС")

    mat = sum(
        (
            _decimal(line.quantity, "Количество") * _decimal(line.price, "Цена")
            for line in materials
        ),
        Decimal(0),
    )
    labor = Decimal(0)
    hours = Decimal(0)
    for op in operations:
        op_hours = _decimal(op.hours, "Трудоёмкость")
        rate = _decimal(op.rate, "Ставка")
        if op.is_supply:
            continue
        labor += op_hours * rate
        hours += op_hours

    overhead = labor * overhead_pct / _HUNDRED
    cost = mat + labor + overhead
    price = cost * (1 + margin_pct / _HUNDRED)
    vat = price * vat_pct / _HUNDRED
    return CalcTotals(
        materials=_store(mat),
        labor=_store(labor),
        hours=_store(hours),
        overhead=_store(overhead),
        cost=_store(cost),
        price=_store(price),
        vat=_store(vat),
        total=_store(price + vat),
        profit=_store(price - cost),
    )
