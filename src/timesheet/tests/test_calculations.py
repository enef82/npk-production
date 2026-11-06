"""Чистые расчёты табеля: деление дня по плану, вытеснение ремонтом, проверки перед
подачей, пакеты 1С — точными числами в `Decimal` (CLAUDE.md §8: количественные
расчёты — там, где генерация кода ошибается чаще всего)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from src.timesheet.calculations import (
    AllocationFact,
    CheckWorker,
    DisplaceableRow,
    PackageFact,
    build_packages,
    compute_checks,
    last_closed_day,
    plan_repair_displacement,
    split_plan_hours,
)
from src.timesheet.tests.support import OCTOBER, SEPTEMBER, TODAY

D = Decimal


def test_восемь_часов_делятся_поровну_с_шагом_полчаса_остаток_на_накладные() -> None:
    assert split_plan_hours(0) == ([], D("8"))
    assert split_plan_hours(1) == ([D("8.0")], D("0.0"))
    assert split_plan_hours(2) == ([D("4.0"), D("4.0")], D("0.0"))
    assert split_plan_hours(3) == ([D("2.5")] * 3, D("0.5"))
    assert split_plan_hours(5) == ([D("1.5")] * 5, D("0.5"))


def test_последний_закрытый_день_месяца() -> None:
    assert last_closed_day(SEPTEMBER, TODAY) == date(2026, 9, 30)
    assert last_closed_day(date(2026, 11, 1), TODAY) == date(2026, 11, 5)
    assert last_closed_day(date(2026, 11, 1), date(2026, 11, 1)) is None
    assert last_closed_day(date(2026, 12, 1), TODAY) is None


def test_ремонт_вытесняет_сначала_накладные_и_простой_затем_крупные_строки() -> None:
    order, overhead, idle = uuid4(), uuid4(), uuid4()
    rows = [
        DisplaceableRow(order, "order", D("5")),
        DisplaceableRow(overhead, "overhead", D("2")),
        DisplaceableRow(idle, "idle", D("1")),
    ]

    assert plan_repair_displacement(rows, D("2.5")) == {overhead: D("0"), idle: D("0.5")}
    assert plan_repair_displacement(rows, D("4")) == {
        overhead: D("0"),
        idle: D("0"),
        order: D("4"),
    }
    assert plan_repair_displacement(rows, D("20")) == {
        overhead: D("0"),
        idle: D("0"),
        order: D("0"),
    }


def _worker(name: str = "Иванов И.И.", *, wc: bool = True) -> CheckWorker:
    return CheckWorker(uuid4(), name, wc, date(2024, 1, 1), None)


def _fact(
    w: CheckWorker, day: int, hours: str, code: str = "Я", target: str = "order"
) -> AllocationFact:
    return AllocationFact(
        w.employee_id, SEPTEMBER.replace(day=day), code, code not in ("ОТ", "Б"), target, D(hours)
    )


def _full_month(w: CheckWorker, skip: tuple[int, ...] = ()) -> list[AllocationFact]:
    weekdays = [d for d in range(1, 31) if SEPTEMBER.replace(day=d).weekday() < 5]
    return [_fact(w, d, "8") for d in weekdays if d not in skip]


def test_полностью_закрытый_месяц_проверки_проходит() -> None:
    w = _worker()
    assert compute_checks([w], _full_month(w), SEPTEMBER, TODAY) == []


def test_не_закрытые_дни_блокируют() -> None:
    w = _worker()
    checks = compute_checks([w], _full_month(w, skip=(3, 4)), SEPTEMBER, TODAY)
    assert [(c.is_blocking, c.text) for c in checks] == [(True, "Иванов И.И.: не закрыты дни 3, 4")]


def test_дни_до_приёма_на_работу_не_требуются() -> None:
    w = CheckWorker(uuid4(), "Новичок", True, date(2026, 9, 7), None)
    facts = [f for f in _full_month(w) if f.date.day >= 7]
    assert compute_checks([w], facts, SEPTEMBER, TODAY) == []


def test_больше_24_часов_в_день_блокирует() -> None:
    w = _worker()
    facts = [*_full_month(w), _fact(w, 1, "10", "С"), _fact(w, 1, "7", "С")]
    checks = compute_checks([w], facts, SEPTEMBER, TODAY)
    assert [(c.is_blocking, c.text) for c in checks] == [
        (True, "Иванов И.И.: больше 24 ч в день (1)")
    ]


def test_часы_сверх_нормы_без_с_или_рв_предупреждение() -> None:
    w = _worker()
    facts = [*_full_month(w), _fact(w, 1, "2")]
    checks = compute_checks([w], facts, SEPTEMBER, TODAY)
    assert [(c.is_blocking, c.text) for c in checks] == [
        (False, "Иванов И.И.: часов больше нормы без пометки «С» или «РВ»")
    ]
    assert compute_checks([w], [*_full_month(w), _fact(w, 1, "2", "С")], SEPTEMBER, TODAY) == []


def test_больше_половины_на_накладные_у_рабочего_предупреждение() -> None:
    w = _worker()
    facts = [
        AllocationFact(f.employee_id, f.date, f.code, f.is_work, "overhead", f.hours)
        if f.date.day <= 15
        else f
        for f in _full_month(w)
    ]
    # 11 дней из 22 на накладных — ровно 50 %, ещё не замечание.
    assert compute_checks([w], facts, SEPTEMBER, TODAY) == []
    facts = [*facts[:-1], _fact(w, 30, "8", target="overhead")]
    checks = compute_checks([w], facts, SEPTEMBER, TODAY)
    assert [c.text for c in checks] == ["Иванов И.И.: 55% часов на накладные — проверьте разноску"]
    # У работника без участка (ИТР) накладные — норма.
    office = _worker("Петров П.П.", wc=False)
    office_facts = [
        AllocationFact(office.employee_id, f.date, f.code, f.is_work, "overhead", f.hours)
        for f in _full_month(office)
    ]
    assert compute_checks([office], office_facts, SEPTEMBER, TODAY) == []


def test_отпуск_закрывает_день_и_входит_в_норму() -> None:
    w = _worker()
    facts = [*_full_month(w, skip=(1,)), _fact(w, 1, "8", "ОТ", "")]
    assert compute_checks([w], facts, SEPTEMBER, TODAY) == []


def test_незаконченный_месяц_блокирует() -> None:
    w = _worker()
    checks = compute_checks([w], [], date(2026, 11, 1), date(2026, 11, 2))
    texts = [(c.is_blocking, c.text) for c in checks]
    assert (True, "Месяц не закончен: осталось 21 рабочих дней") in texts
    assert (True, "Иванов И.И.: не закрыты дни ") not in texts


def _pf(
    no: str, day: int, code: str, target: str, hours: str, order: UUID | None = None
) -> PackageFact:
    return PackageFact(no, OCTOBER.replace(day=day), code, code != "ОТ", target, order, D(hours))


def test_пакеты_1с_точные_часы_и_доли() -> None:
    order_a, order_b = uuid4(), UUID(int=11)  # «000…0b» сортируется раньше «OVH»
    facts = [
        _pf("0002", 1, "Я", "order", "6", order_a),
        _pf("0002", 1, "Я", "overhead", "2"),
        _pf("0002", 2, "Я", "order", "8", order_a),
        _pf("0002", 3, "С", "order", "2", order_a),
        _pf("0002", 5, "ОТ", "", "8"),
        _pf("0001", 1, "Я", "order", "8", order_a),
        _pf("0001", 2, "Я", "order", "8", order_b),
        _pf("0001", 5, "Я", "overhead", "8"),
    ]

    timesheet, cost = build_packages(
        facts,
        month=OCTOBER,
        department_code="SMU",
        version=2,
        order_numbers={order_a: "ПЗ-2026-0001"},
    )

    base = {"period": {"year": 2026, "month": 10}, "department_code": "SMU", "version": 2}
    assert timesheet == {
        "package_type": "timesheet",
        **base,
        "entries": [
            {"employee_code": "0001", "date": "2026-10-01", "time_code": "Я", "hours": "8.00"},
            {"employee_code": "0001", "date": "2026-10-02", "time_code": "Я", "hours": "8.00"},
            {"employee_code": "0001", "date": "2026-10-05", "time_code": "Я", "hours": "8.00"},
            {"employee_code": "0002", "date": "2026-10-01", "time_code": "Я", "hours": "8.00"},
            {"employee_code": "0002", "date": "2026-10-02", "time_code": "Я", "hours": "8.00"},
            {"employee_code": "0002", "date": "2026-10-03", "time_code": "С", "hours": "2.00"},
            {"employee_code": "0002", "date": "2026-10-05", "time_code": "ОТ", "hours": "8.00"},
        ],
    }
    # 0001 — по трети на три аналитики: 0,3333 × 3 = 0,9999, остаток ложится на первую
    # из самых больших строк (аналитики по алфавиту), сумма долей — ровно 1. Заказ без
    # номера в `production` — аналитика его UUID.
    assert cost == {
        "package_type": "cost_allocation",
        **base,
        "rows": [
            {
                "employee_code": "0001",
                "analytics": str(order_b),
                "hours": "8.00",
                "share": "0.3334",
            },
            {"employee_code": "0001", "analytics": "OVH-SMU", "hours": "8.00", "share": "0.3333"},
            {
                "employee_code": "0001",
                "analytics": "ПЗ-2026-0001",
                "hours": "8.00",
                "share": "0.3333",
            },
            {"employee_code": "0002", "analytics": "OVH-SMU", "hours": "2.00", "share": "0.1111"},
            {
                "employee_code": "0002",
                "analytics": "ПЗ-2026-0001",
                "hours": "16.00",
                "share": "0.8889",
            },
        ],
    }
    for no in ("0001", "0002"):
        assert sum(D(r["share"]) for r in cost["rows"] if r["employee_code"] == no) == D("1")
