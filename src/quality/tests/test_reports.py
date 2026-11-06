"""Отчёты ОТК (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3): по участку и неделе,
Парето причин и видов, динамика 12 недель с разделением на промежуточный и финальный
контроль, доля брака по вине оператора; фасад для `production` и `analytics`."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.quality import facade, selectors
from src.quality.models import DefectCause
from src.quality.tests.factories import (
    DefectTypeFactory,
    InspectionPointFactory,
    InspectionRecordFactory,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 10, 26)


def _cause(name: str) -> DefectCause:
    return DefectCause.objects.get(name=name)


def test_агрегат_по_операции_считает_брак_и_вину_оператора() -> None:
    op = uuid.uuid4()
    defect = DefectTypeFactory.create()
    InspectionRecordFactory.create(operation_id=op, checked=20)
    InspectionRecordFactory.create(
        operation_id=op, checked=5, rework=2, scrap=1, defect_type=defect, cause=_cause("Оператор")
    )
    InspectionRecordFactory.create(
        operation_id=op, checked=4, rework=1, defect_type=defect, cause=_cause("Оборудование")
    )

    agg = facade.get_qc_by_operation([op, uuid.uuid4()])

    assert list(agg) == [op]
    assert (agg[op].checked, agg[op].rework, agg[op].scrap, agg[op].defects) == (29, 3, 1, 4)
    assert agg[op].operator_defects == 3
    assert selectors.qc_by_operation([op])[op].pct == Decimal("13.8")


def test_по_неделе_и_участку_с_понедельника() -> None:
    point = InspectionPointFactory.create(is_final=True)
    wc = point.work_center_id
    defect = DefectTypeFactory.create(inspection_point=point)
    InspectionRecordFactory.create(work_center_id=wc, date=MONDAY, checked=10)
    InspectionRecordFactory.create(
        work_center_id=wc,
        date=date(2026, 11, 1),  # воскресенье — та же неделя
        checked=2,
        scrap=2,
        defect_type=defect,
        cause=_cause("Технология"),
    )
    InspectionRecordFactory.create(work_center_id=wc, date=date(2026, 11, 2), checked=7)

    rows = facade.list_qc_by_week(MONDAY, date(2026, 11, 8))

    assert [(r.week_start, r.checked, r.scrap, r.is_final) for r in rows] == [
        (MONDAY, 12, 2, True),
        (date(2026, 11, 2), 7, 0, True),
    ]


def test_парето_по_причинам_с_накопленной_долей() -> None:
    defect = DefectTypeFactory.create(name="поры")
    other = DefectTypeFactory.create(name="непровар")
    for cause, defects, kind in (("Оператор", 6, defect), ("КД / УП ЧПУ", 3, other)):
        InspectionRecordFactory.create(
            date=MONDAY, checked=10, rework=defects, defect_type=kind, cause=_cause(cause)
        )
    InspectionRecordFactory.create(
        date=MONDAY, checked=10, scrap=1, defect_type=other, cause=_cause("Прочее")
    )

    causes = selectors.pareto_causes(MONDAY, date(2026, 11, 1))
    kinds = selectors.pareto_defect_types(MONDAY, date(2026, 11, 1))

    assert [(r.name, r.defects, r.cumulative_pct) for r in causes] == [
        ("Оператор", 6, Decimal("60.0")),
        ("КД / УП ЧПУ", 3, Decimal("90.0")),
        ("Прочее", 1, Decimal("100.0")),
    ]
    assert [(r.name, r.defects) for r in kinds] == [("поры", 6), ("непровар", 4)]


def test_динамика_делит_брак_на_промежуточный_и_финальный() -> None:
    final = InspectionPointFactory.create(is_final=True)
    inter = InspectionPointFactory.create()
    for point, defects in ((final, 1), (inter, 3)):
        InspectionRecordFactory.create(
            work_center_id=point.work_center_id,
            date=MONDAY,
            checked=20,
            rework=defects,
            defect_type=DefectTypeFactory.create(inspection_point=point),
            cause=_cause("Прочее"),
        )

    weeks = selectors.last_weeks(date(2026, 11, 4), 12)
    rows = selectors.dynamics(weeks)

    assert len(rows) == 12
    assert weeks[-1] == date(2026, 11, 2)
    week = next(r for r in rows if r.week_start == MONDAY)
    assert (week.checked, week.intermediate_defects, week.final_defects, week.pct) == (
        40,
        3,
        1,
        Decimal("10.0"),
    )


def test_сводка_по_точкам_с_главным_дефектом_и_трендом() -> None:
    point = InspectionPointFactory.create()
    defect = DefectTypeFactory.create(inspection_point=point, name="заусенцы")
    weeks = selectors.last_weeks(date(2026, 11, 4), 4)
    InspectionRecordFactory.create(work_center_id=point.work_center_id, date=weeks[0], checked=50)
    InspectionRecordFactory.create(
        work_center_id=point.work_center_id,
        date=weeks[3],
        checked=50,
        rework=5,
        defect_type=defect,
        cause=_cause("Оператор"),
    )

    (row,) = [r for r in selectors.summary_by_work_center(weeks) if r.point == point]

    assert row.totals.checked == 100
    assert row.top_defect == ("заусенцы", 5)
    assert row.trend == Decimal("10.0")


def test_requires_inspection_только_у_действующей_точки() -> None:
    point = InspectionPointFactory.create()
    inactive = InspectionPointFactory.create(is_active=False)

    assert facade.requires_inspection(point.work_center_id) is True
    assert facade.requires_inspection(inactive.work_center_id) is False
    assert facade.requires_inspection(uuid.uuid4()) is False


def test_has_inspection_по_наличию_записи() -> None:
    record = InspectionRecordFactory.create()

    assert facade.has_inspection(record.operation_id) is True
    assert facade.has_inspection(uuid.uuid4()) is False


def test_агрегат_по_операциям_за_период_берёт_только_записи_периода() -> None:
    op = uuid.uuid4()
    defect = DefectTypeFactory.create()
    InspectionRecordFactory.create(
        operation_id=op,
        date=MONDAY,
        checked=6,
        rework=2,
        defect_type=defect,
        cause=_cause("Оператор"),
    )
    InspectionRecordFactory.create(operation_id=op, date=MONDAY - timedelta(days=1), checked=50)

    result = facade.list_qc_by_operation(MONDAY, MONDAY + timedelta(days=6))

    assert result == {op: facade.QcAgg(checked=6, rework=2, scrap=0, operator_defects=2)}
