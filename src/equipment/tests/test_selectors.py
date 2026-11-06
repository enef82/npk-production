"""Отчёты экрана «Оборудование»: моточасы, состояние ТО, неделя, Парето, журнал."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from src.equipment import selectors
from src.equipment.calculations import week_start
from src.equipment.models import MaintenanceState, RepairKind, RepairStatus
from src.equipment.tests.factories import (
    DownReasonFactory,
    EquipmentFactory,
    FailureCategoryFactory,
    IdleReasonFactory,
    MaintenanceRecordFactory,
    MaintenanceTypeFactory,
    RepairFactory,
    RepairWorkerFactory,
    RuntimeLogFactory,
)

pytestmark = pytest.mark.django_db


def _monday_last_week() -> date:
    return week_start(timezone.localdate()) - timedelta(weeks=1)


def test_моточасы_это_начальные_плюс_работа_по_журналу() -> None:
    equipment = EquipmentFactory.create(operating_hours_initial=Decimal("2500"))
    monday = _monday_last_week()
    RuntimeLogFactory.create(equipment=equipment, date=monday, run=Decimal("6.5"))
    RuntimeLogFactory.create(equipment=equipment, date=monday + timedelta(days=1), run=Decimal("7"))

    found = selectors.get_equipment(equipment.id)

    assert found is not None
    assert selectors.operating_hours(found) == Decimal("2513.50")


def test_состояние_то_выводится_от_последнего_проведённого() -> None:
    equipment = EquipmentFactory.create(operating_hours_initial=Decimal("1262"))
    overdue = MaintenanceTypeFactory.create(
        equipment=equipment, code="ТО-1", interval_hours=Decimal("250")
    )
    MaintenanceRecordFactory.create(maintenance_type=overdue, at_hours=Decimal("1000"))
    fresh = MaintenanceTypeFactory.create(
        equipment=equipment, code="ТО-2", interval_hours=Decimal("1000")
    )
    MaintenanceRecordFactory.create(maintenance_type=fresh, at_hours=Decimal("1200"))
    found = selectors.get_equipment(equipment.id)
    assert found is not None

    rows = selectors.maintenance_by_equipment([found], timezone.localdate())[equipment.id]

    assert [row.maintenance_type.code for row in rows] == ["ТО-1", "ТО-2"]
    assert rows[0].forecast.state == MaintenanceState.OVERDUE
    assert rows[0].forecast.hours_left == Decimal("-12.0")
    assert rows[0].last_at_hours == Decimal("1000.00")
    assert rows[1].forecast.state == MaintenanceState.OK
    assert rows[1].forecast.next_at_hours == Decimal("2200.0")


def test_недельная_сводка_и_парето_простоев() -> None:
    equipment = EquipmentFactory.create()
    monday = _monday_last_week()
    no_task = IdleReasonFactory.create(name="Нет задания")
    material = IdleReasonFactory.create(name="Ожидание материала")
    failure = DownReasonFactory.create(repair_kind=RepairKind.FAILURE)
    RuntimeLogFactory.create(
        equipment=equipment, date=monday, run=Decimal("5"), idle=Decimal("3"), idle_reason=no_task
    )
    RuntimeLogFactory.create(
        equipment=equipment,
        date=monday + timedelta(days=1),
        run=Decimal("3"),
        idle=Decimal("1"),
        idle_reason=material,
        down=Decimal("4"),
        down_reason=failure,
    )

    week = selectors.week_summaries([equipment.id], [monday])[equipment.id][monday]
    pareto = selectors.downtime_pareto(monday, monday + timedelta(days=6))

    assert (week.run, week.idle, week.down, week.days) == (
        Decimal("8.00"),
        Decimal("4.00"),
        Decimal("4.00"),
        2,
    )
    assert week.utilization == Decimal("0.5000")
    assert [(row.reason, row.is_down, row.hours) for row in pareto] == [
        (failure.name, True, Decimal("4.00")),
        ("Нет задания", False, Decimal("3.00")),
        ("Ожидание материала", False, Decimal("1.00")),
    ]


def test_журнал_показывает_незакрытые_всегда_и_считает_трудозатраты() -> None:
    now = timezone.now()
    category = FailureCategoryFactory.create(name="Гидравлика")
    old_open = RepairFactory.create(started_at=now - timedelta(days=200))
    recent = RepairFactory.create(
        started_at=now - timedelta(days=3),
        finished_at=now - timedelta(days=3) + timedelta(hours=2),
        status=RepairStatus.DONE,
        category=category,
    )
    RepairFactory.create(
        started_at=now - timedelta(days=200),
        finished_at=now - timedelta(days=200) + timedelta(hours=1),
        status=RepairStatus.DONE,
        category=category,
    )
    RepairWorkerFactory.create(repair=recent, hours=Decimal("1.5"))
    RepairWorkerFactory.create(repair=recent, hours=Decimal("2"))
    for back in (1, 2):
        RuntimeLogFactory.create(
            equipment=recent.equipment,
            date=timezone.localdate() - timedelta(days=back),
            run=Decimal("20"),
        )
    date_from = timezone.localdate() - timedelta(days=90)

    repairs = list(selectors.list_repairs(date_from=date_from))
    summary = selectors.summarize_repairs(repairs, date_from=date_from, equipment_id=None, now=now)

    assert {r.id for r in repairs} == {old_open.id, recent.id}
    labor = {r.id: selectors.repair_labor(r) for r in repairs}
    assert labor[recent.id] == Decimal("3.50")
    assert summary.failures == 2
    assert summary.mttr == Decimal("2.0")
    assert summary.mtbf == Decimal("20")  # 40 машино-часов / 2 аварии
    assert summary.downtime_by_category == [("Гидравлика", Decimal("2.0"))]


def test_список_оборудования_не_делает_n_plus_1(django_assert_max_num_queries) -> None:  # type: ignore[no-untyped-def]
    def build(count: int) -> None:
        for _ in range(count):
            equipment = EquipmentFactory.create()
            mtype = MaintenanceTypeFactory.create(equipment=equipment)
            MaintenanceRecordFactory.create(maintenance_type=mtype)
            RuntimeLogFactory.create(equipment=equipment)

    build(2)
    with django_assert_max_num_queries(3):
        equipment = list(selectors.list_equipment())
        selectors.maintenance_by_equipment(equipment, timezone.localdate())
    build(5)
    with django_assert_max_num_queries(3):
        equipment = list(selectors.list_equipment())
        selectors.maintenance_by_equipment(equipment, timezone.localdate())
