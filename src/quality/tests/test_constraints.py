"""Ограничения БД модуля «ОТК и качество»: попытка нарушить → `IntegrityError`
(CLAUDE.md §8), и состав справочника причин из миграции."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from src.quality.models import DefectCause
from src.quality.tests.factories import (
    DefectCauseFactory,
    DefectTypeFactory,
    InspectionPointFactory,
    InspectionRecordFactory,
)

pytestmark = pytest.mark.django_db


def test_нельзя_записать_контроль_без_проверенных() -> None:
    with pytest.raises(IntegrityError, match="quality_record_checked_positive"):
        InspectionRecordFactory.create(checked=0)


def test_брака_не_может_быть_больше_чем_проверено() -> None:
    defect = DefectTypeFactory.create()
    cause = DefectCauseFactory.create()
    with pytest.raises(IntegrityError, match="quality_record_defects_within_checked"):
        InspectionRecordFactory.create(
            checked=3, rework=2, scrap=2, defect_type=defect, cause=cause
        )


def test_брак_равный_проверенному_допустим() -> None:
    record = InspectionRecordFactory.create(
        checked=3,
        rework=1,
        scrap=2,
        defect_type=DefectTypeFactory.create(),
        cause=DefectCauseFactory.create(),
    )
    assert record.defects == 3


@pytest.mark.parametrize("missing", ["defect_type", "cause"])
def test_брак_без_вида_дефекта_или_причины_нарушает_constraint(missing: str) -> None:
    values: dict[str, object] = {
        "defect_type": DefectTypeFactory.create(),
        "cause": DefectCauseFactory.create(),
    }
    values[missing] = None
    with pytest.raises(IntegrityError, match="quality_record_defect_classified"):
        InspectionRecordFactory.create(checked=5, rework=1, **values)


def test_у_участка_одна_точка_контроля() -> None:
    point = InspectionPointFactory.create()
    with pytest.raises(IntegrityError):
        InspectionPointFactory.create(work_center_id=point.work_center_id)


def test_вид_дефекта_уникален_в_точке_контроля() -> None:
    defect = DefectTypeFactory.create(name="поры")
    DefectTypeFactory.create(name="поры")  # у другой точки — можно
    with pytest.raises(IntegrityError):
        DefectTypeFactory.create(name="поры", inspection_point=defect.inspection_point)


def test_миграция_засевает_причины_прототипа_с_признаком_оператора() -> None:
    causes = {c.name: c.is_operator_fault for c in DefectCause.objects.all()}
    assert causes == {
        "Оператор": True,
        "Оборудование": False,
        "Материал / комплектующие": False,
        "КД / УП ЧПУ": False,
        "Технология": False,
        "Прочее": False,
    }
