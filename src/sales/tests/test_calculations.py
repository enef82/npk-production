"""Итоги калькуляции (`calcTotals` прототипа) — чистые функции, без БД. Деньги — только
Decimal (И6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.sales.calculations import LaborLine, MaterialLine, calc_totals

D = Decimal


def test_итоги_калькуляции_по_формулам_прототипа() -> None:
    t = calc_totals(
        [MaterialLine(D("2"), D("68000")), MaterialLine(D("1.5"), D("1000.10"))],
        [
            LaborLine(D("24"), D("1800"), is_supply=False),
            LaborLine(D("15"), D("0"), is_supply=True),
            LaborLine(D("32.5"), D("1300"), is_supply=False),
        ],
        overhead_pct=D("25"),
        margin_pct=D("20"),
        vat_pct=D("22"),
    )
    # материалы 136000 + 1500.15; труд 43200 + 42250; накладные 25 % труда
    assert t.materials == D("137500.1500")
    assert t.labor == D("85450.0000")
    assert t.hours == D("56.5000")
    assert t.overhead == D("21362.5000")
    assert t.cost == D("244312.6500")
    assert t.price == D("293175.1800")
    assert t.vat == D("64498.5396")
    assert t.total == D("357673.7196")
    assert t.profit == D("48862.5300")


def test_снабжение_не_входит_ни_в_труд_ни_в_часы() -> None:
    t = calc_totals(
        [],
        [LaborLine(D("30"), D("2000"), is_supply=True)],
        overhead_pct=D("25"),
        margin_pct=D("20"),
        vat_pct=D("22"),
    )
    assert (t.labor, t.hours, t.total) == (D("0.0000"), D("0.0000"), D("0.0000"))


def test_проценты_передаются_в_процентах_а_не_долях() -> None:
    t = calc_totals(
        [MaterialLine(D("1"), D("100"))],
        [],
        overhead_pct=D("0"),
        margin_pct=D("20"),
        vat_pct=D("0"),
    )
    assert t.price == D("120.0000")


def test_округление_до_четырёх_знаков_половина_вверх() -> None:
    t = calc_totals(
        [MaterialLine(D("0.001"), D("0.05"))],
        [],
        overhead_pct=D("0"),
        margin_pct=D("0"),
        vat_pct=D("0"),
    )
    assert t.materials == D("0.0001")  # 0.00005 → 0.0001


def test_float_запрещён() -> None:
    with pytest.raises(TypeError):
        calc_totals(
            [MaterialLine(1.5, D("10"))],  # type: ignore[arg-type]
            [],
            overhead_pct=D("0"),
            margin_pct=D("0"),
            vat_pct=D("0"),
        )
    with pytest.raises(TypeError):
        calc_totals([], [], overhead_pct=25.0, margin_pct=D("0"), vat_pct=D("0"))  # type: ignore[arg-type]
