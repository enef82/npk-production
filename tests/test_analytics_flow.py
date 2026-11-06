"""Аналитика (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8) на настоящих данных
`production`, `timesheet`, `quality`, `sales`: живая неделя и снимок отсечки, права на
закрытие, распределение освоения по сотрудникам в часах и рублях, загрузка 10 недель,
портфель с вероятностями этапов, число запросов основных отчётов. Корневой `tests/` —
нужны модели нескольких модулей."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.analytics import calculations as calc
from src.analytics import selectors
from src.analytics.exceptions import CutoffAlreadyClosed, FutureWeek, ReasonRequired
from src.analytics.models import CutoffAction, WeeklyCutoff, WeeklyCutoffEvent, WeeklyCutoffRow
from src.analytics.services import cutoff as cutoff_services
from src.core.accounts.groups import OBSERVER, PRODUCTION_HEAD
from src.core.accounts.tests.factories import UserFactory
from src.core.common.scheduling import add_working_days
from src.core.org.models import Employee
from src.core.org.tests.factories import EmployeeFactory
from src.production.models import (
    Operation,
    OperationEarning,
    OperationStatus,
    OrderStage,
    ProductionOrder,
)
from src.production.tests.support import (
    Plant,
    client_for,
    launch_order,
    make_plant,
    user_with_employee,
)
from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord
from src.sales.models import InquiryStage
from src.sales.services import calculation as sales_calc
from src.timesheet.models import AllocationTarget, TimeCode, WorkAllocation, WorkerProfile
from tests.sales_support import make_inquiry, make_shop

pytestmark = pytest.mark.django_db

BASE = "/api/v1/analytics"


def _today() -> date:
    return timezone.localdate()


def _last_week() -> date:
    return calc.week_start(_today()) - timedelta(weeks=1)


def _op(order: ProductionOrder, name: str) -> Operation:
    return Operation.objects.get(order=order, name=name)


def _worker(plant_center_id: Any, rate: str) -> Employee:
    employee = EmployeeFactory.create()
    WorkerProfile.objects.create(
        employee=employee, work_center_id=plant_center_id, hourly_rate=Decimal(rate)
    )
    return employee


def _allocate(
    employee: Employee,
    day: date,
    hours: str,
    op: Operation | None = None,
    *,
    code: str = "Я",
    target: str = AllocationTarget.ORDER,
) -> None:
    WorkAllocation.objects.create(
        employee=employee,
        date=day,
        time_code=TimeCode.objects.get(code=code),
        target=target,
        order_id=op.order_id if op else None,
        operation_id=op.id if op else None,
        hours=Decimal(hours),
    )


def _inspect(op: Operation, day: date, checked: int, rework: int = 0) -> None:
    point, _ = InspectionPoint.objects.get_or_create(
        work_center_id=op.work_center_id, defaults={"name": "Контроль сборки"}
    )
    defect = DefectType.objects.get_or_create(inspection_point=point, name="ошибка сборки")[0]
    InspectionRecord.objects.create(
        operation_id=op.id,
        order_id=op.order_id,
        work_center_id=op.work_center_id,
        date=day,
        inspector=EmployeeFactory.create(),
        checked=checked,
        rework=rework,
        defect_type=defect if rework else None,
        cause=DefectCause.objects.get(name="Оператор") if rework else None,
    )


def _week_with_data(plant: Plant) -> tuple[ProductionOrder, date]:
    """Прошлая неделя: КД (8 ч) в понедельник, Сборка (16 ч, 2 чел.) во вторник;
    освоено 12 н-ч Сборки, отработано 16 ч на участке сборки, проверено 5, брак 1."""

    week = _last_week()
    order = launch_order(plant=plant)
    Operation.objects.filter(id=_op(order, "КД").id).update(planned_start=week)
    Operation.objects.filter(id=_op(order, "Сборка").id).update(
        planned_start=week + timedelta(days=1)
    )
    Operation.objects.filter(id=_op(order, "ОТК").id).update(planned_start=None)
    assembly = _op(order, "Сборка")
    OperationEarning.objects.create(
        operation=assembly, date=week + timedelta(days=1), hours=Decimal("12")
    )
    worker = _worker(plant.prod.id, "1000")
    _allocate(worker, week + timedelta(days=1), "8", assembly)
    _allocate(worker, week + timedelta(days=2), "8", target=AllocationTarget.OVERHEAD)
    _inspect(assembly, week + timedelta(days=1), checked=5, rework=1)
    return order, week


def _row(week: selectors.CutoffWeek, center_id: Any) -> selectors.CutoffRow:
    return next(r for r in week.rows if r.work_center_id == center_id)


# --- Живая неделя и снимок -----------------------------------------------------------


def test_живая_неделя_план_освоено_отработано_и_брак_по_участку() -> None:
    plant = make_plant()
    _, week = _week_with_data(plant)

    [live] = selectors.cutoff_weeks([week], worked_for=[week])
    prod = _row(live, plant.prod.id)

    assert (prod.planned, prod.earned, prod.worked) == (
        Decimal("16.00"),
        Decimal("12.00"),
        Decimal("16.00"),
    )
    assert (prod.plan_pct, prod.output_pct) == (Decimal("75.0"), Decimal("75.0"))
    # Мощность 3 исполнителя × 40 ч; загрузка = план ÷ мощность.
    assert (prod.capacity, prod.load_pct) == (Decimal("120"), Decimal("13.3"))
    assert (prod.checked, prod.defects, prod.defect_pct) == (5, 1, Decimal("20.0"))
    assert _row(live, plant.prep.id).planned == Decimal("8.00")
    assert live.total.planned == Decimal("24.00")
    assert live.status == "open"


def test_снимок_закрытой_недели_не_меняется_от_новых_данных() -> None:
    plant = make_plant()
    order, week = _week_with_data(plant)
    head = EmployeeFactory.create()

    cutoff_services.close_week(week, actor_employee_id=head.id, comment="простой лазера 6 ч")
    OperationEarning.objects.create(
        operation=_op(order, "Сборка"), date=week + timedelta(days=2), hours=Decimal("4")
    )

    [closed] = selectors.cutoff_weeks([week])
    assert closed.status == "closed"
    assert closed.comment == "простой лазера 6 ч"
    assert _row(closed, plant.prod.id).earned == Decimal("12.00")
    snapshot = WeeklyCutoffRow.objects.get(cutoff__week_start=week, work_center_id=plant.prod.id)
    with pytest.raises(IntegrityError), transaction.atomic():
        WeeklyCutoffRow.objects.filter(id=snapshot.id).update(earned_hours=Decimal("16"))
    with pytest.raises(CutoffAlreadyClosed):
        cutoff_services.close_week(week, actor_employee_id=head.id)

    cutoff_services.reopen_week(week, actor_employee_id=head.id, reason="не учли переделку")

    [reopened] = selectors.cutoff_weeks([week])
    assert reopened.status == "open"
    assert _row(reopened, plant.prod.id).earned == Decimal("16.00")
    assert list(
        WeeklyCutoffEvent.objects.filter(week_start=week)
        .order_by("created_at")
        .values_list("action", "text")
    ) == [(CutoffAction.CLOSE, "простой лазера 6 ч"), (CutoffAction.REOPEN, "не учли переделку")]


def test_отработанные_часы_при_закрытии_можно_поправить_поверх_табеля() -> None:
    plant = make_plant()
    _, week = _week_with_data(plant)

    cutoff_services.close_week(
        week,
        actor_employee_id=EmployeeFactory.create().id,
        worked_hours={plant.prod.id: Decimal("24")},
    )

    row = WeeklyCutoffRow.objects.get(cutoff__week_start=week, work_center_id=plant.prod.id)
    assert (row.worked_hours, row.planned_hours, row.earned_hours) == (
        Decimal("24.00"),
        Decimal("16.00"),
        Decimal("12.00"),
    )


def test_будущую_неделю_закрыть_нельзя_а_переоткрыть_без_причины_нельзя() -> None:
    plant = make_plant()
    _, week = _week_with_data(plant)
    head = EmployeeFactory.create()
    with pytest.raises(FutureWeek):
        cutoff_services.close_week(
            calc.week_start(_today()) + timedelta(weeks=1), actor_employee_id=head.id
        )
    cutoff_services.close_week(week, actor_employee_id=head.id)
    with pytest.raises(ReasonRequired):
        cutoff_services.reopen_week(week, actor_employee_id=head.id, reason="   ")
    assert WeeklyCutoff.objects.filter(week_start=week).exists()


# --- Права на закрытие ---------------------------------------------------------------


def test_начальник_производства_закрывает_и_переоткрывает_отсечку() -> None:
    plant = make_plant()
    _, week = _week_with_data(plant)
    user, employee = user_with_employee(PRODUCTION_HEAD)
    client = client_for(user)

    overview = client.get(f"{BASE}/cutoffs", {"week": week.isoformat()}).json()
    assert overview["abilities"]["can_close"] is True

    response = client.post(
        f"{BASE}/cutoffs",
        {"week_start": week.isoformat(), "comment": "", "worked": []},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert WeeklyCutoff.objects.get(week_start=week).closed_by_id == employee.id

    response = client.post(
        f"{BASE}/cutoffs/{week.isoformat()}/reopen",
        {"reason": "ошибка в табеле"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert not WeeklyCutoff.objects.filter(week_start=week).exists()


def test_наблюдатель_видит_отсечки_но_не_закрывает_и_не_переоткрывает() -> None:
    plant = make_plant()
    _, week = _week_with_data(plant)
    WeeklyCutoff.objects.create(
        week_start=week - timedelta(weeks=1),
        closed_by=EmployeeFactory.create(),
        closed_at=timezone.now(),
    )
    user, _ = user_with_employee(OBSERVER)
    client = client_for(user)

    overview = client.get(f"{BASE}/cutoffs").json()
    assert overview["abilities"]["can_close"] is False
    assert overview["selected_week"] == calc.week_start(_today()).isoformat()

    response = client.post(
        f"{BASE}/cutoffs",
        {"week_start": week.isoformat()},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not WeeklyCutoff.objects.filter(week_start=week).exists()
    response = client.post(
        f"{BASE}/cutoffs/{(week - timedelta(weeks=1)).isoformat()}/reopen",
        {"reason": "хочу"},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert WeeklyCutoff.objects.filter(week_start=week - timedelta(weeks=1)).exists()


def test_аноним_отчёты_не_читает() -> None:
    from django.test import Client

    assert Client().get(f"{BASE}/portfolio").status_code == 401


# --- Сотрудники ----------------------------------------------------------------------


def test_освоение_операции_делится_между_сотрудниками_по_часам_и_в_рублях() -> None:
    plant = make_plant()  # ставка участка сборки 1500 ₽ (фабрика)
    order = launch_order(plant=plant)
    assembly = _op(order, "Сборка")
    day = _today() - timedelta(days=7)
    a = _worker(plant.prod.id, "1000")
    b = _worker(plant.prod.id, "1200")
    _allocate(a, day, "6", assembly)
    _allocate(b, day, "2", assembly, code="С")  # сверхурочные × 1,5
    OperationEarning.objects.create(operation=assembly, date=day, hours=Decimal("10"))
    _inspect(assembly, day, checked=4, rework=2)

    client = client_for(UserFactory.create())
    report = client.get(f"{BASE}/employees", {"period": "4w"}).json()
    rows = {r["employee_id"]: r["stats"] for r in report["rows"]}
    sa, sb = rows[str(a.id)], rows[str(b.id)]

    assert (sa["earned"], sb["earned"]) == ("7.50", "2.50")
    assert (sa["rub"], sb["rub"]) == ("11250.00", "3750.00")
    assert (sa["cost"], sb["cost"]) == ("6000.00", "3600.00")
    assert (sa["return_ratio"], sb["return_ratio"]) == ("1.88", "1.04")
    assert (sa["overtime"], sb["overtime"]) == ("0.00", "2.00")
    assert (sa["defects"], sa["operator_defects"], sb["defects"]) == ("1.50", "1.50", "0.50")
    assert (sa["output_pct"], sa["productivity_pct"]) == ("125.0", "125.0")
    assert report["total"]["rub"] == "15000.00"
    assert report["unattributed"] == "0.00"

    card = client.get(f"{BASE}/employees/{a.id}", {"period": "4w"}).json()
    [op_row] = card["operations"]
    assert (op_row["order_number"], op_row["operation_name"]) == (order.number, "Сборка")
    assert (op_row["hours"], op_row["earned"], op_row["rub"]) == ("6.00", "7.50", "11250.00")
    assert [w["week_start"] for w in card["weeks"]] == [calc.week_start(day).isoformat()]


# --- Загрузка и портфель -------------------------------------------------------------


def _planned_inquiry(stage: InquiryStage) -> Any:
    """Заявка «КД 24 ч → Закупка 15 дн → Сборка 16 ч» с планом от понедельника следующей
    недели (`tests/sales_support.make_shop`)."""

    shop = make_shop()
    inquiry = make_inquiry(shop, quantity="1")
    actor = UserFactory.create().id
    sales_calc.fill_from_template(inquiry.id, None, actor_id=actor)
    start = calc.week_start(_today()) + timedelta(weeks=1)
    sales_calc.build_plan(inquiry.id, start, actor_id=actor)
    type(inquiry).objects.filter(id=inquiry.id).update(stage=stage)
    return shop, inquiry, start


def test_загрузка_10_недель_заказы_твёрдо_заявки_предварительно() -> None:
    plant = make_plant()
    order = launch_order(plant=plant)
    shop, _, start = _planned_inquiry(InquiryStage.CALC)
    assembly = _op(order, "Сборка")
    Operation.objects.filter(id=assembly.id).update(
        status=OperationStatus.WORK, progress=50, started_at=timezone.now()
    )

    grid = selectors.load_grid()
    rows = {r.work_center_id: r for r in grid.rows}
    week_index = {w: i for i, w in enumerate(grid.weeks)}

    # Заказ: остаток Сборки 16 × (1 − 50 %) = 8 ч в неделю её плана.
    assert assembly.planned_start is not None
    cell = rows[plant.prod.id].cells[week_index[calc.week_start(assembly.planned_start)]]
    assert (cell.firm, cell.tentative) == (Decimal("8.00"), Decimal("0.00"))
    # Заявка: КД 24 ч в первую неделю плана — предварительно, без вероятности.
    kd_cell = rows[shop.kb.id].cells[week_index[start]]
    assert (kd_cell.firm, kd_cell.tentative) == (Decimal("0.00"), Decimal("24.00"))
    # Снабжение в загрузку не входит.
    assert shop.snab.id not in rows
    assert rows[plant.prod.id].capacity == Decimal("120")


def test_портфель_твёрдо_по_заказам_воронка_по_вероятности_этапа() -> None:
    plant = make_plant()
    order = launch_order(plant=plant)
    _, inquiry, _ = _planned_inquiry(InquiryStage.CALC)

    data = selectors.portfolio()
    items = {item.id: item for item in data.items}

    firm = items[order.id]
    assert (firm.total, firm.probability, firm.kind) == (Decimal("1000000"), Decimal(1), "firm")
    pipe = items[inquiry.id]
    # Итог заявки: материалы 68 000 + труд 64 000 + накладные 25 % → × 1,2 наценка → + НДС 22 %.
    assert pipe.total == Decimal("216672.0000")
    assert pipe.probability == Decimal("0.3")
    assert pipe.weighted == Decimal("65001.60")
    month_revenue = data.revenue[data.months.index(pipe.month)]
    assert month_revenue.pipe == Decimal("65001.60")
    assert data.revenue[data.months.index(firm.month)].firm == Decimal("1000000")
    assert data.probabilities[InquiryStage.CALC] == Decimal("30")

    # Загрузка воронки — часы плана × вероятность: КД 24 × 0,3 + Сборка 16 × 0,3 = 12.
    pipe_hours = sum((m.pipe for m in data.load), Decimal(0))
    assert pipe_hours == Decimal("12.0")
    # Мощность месяца — исполнители × 8 × рабочие дни, по всем участкам.
    month = data.months[2]
    assert data.capacity[2] == sum(
        (
            Decimal(c) * 8 * calc.working_days_in_month(month)
            for c in (plant.prep.capacity, plant.prod.capacity, plant.qc.capacity, 1, 2)
        ),
        Decimal(0),
    )


def test_отгруженный_заказ_в_портфеле_фактом_месяца_отгрузки() -> None:
    plant = make_plant()
    order = launch_order(plant=plant)
    shipped = timezone.now() - timedelta(days=1)
    ProductionOrder.objects.filter(id=order.id).update(stage=OrderStage.DONE, shipped_at=shipped)

    data = selectors.portfolio()

    [item] = [i for i in data.items if i.id == order.id]
    assert item.kind == "fact"
    month = calc.month_start(timezone.localtime(shipped).date())
    assert data.revenue[data.months.index(month)].fact == Decimal("1000000")


# --- Число запросов не зависит от объёма данных ----------------------------------------


def _orders_with_work(plant: Plant, n: int) -> None:
    day = _today() - timedelta(days=3)
    for _ in range(n):
        order = launch_order(plant=plant, planned_start=add_working_days(_today(), 1))
        assembly = _op(order, "Сборка")
        OperationEarning.objects.create(operation=assembly, date=day, hours=Decimal("2"))
        worker = _worker(plant.prod.id, "1000")
        _allocate(worker, day, "4", assembly)
        _inspect(assembly, day, checked=2)


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/cutoffs",
        f"{BASE}/load",
        f"{BASE}/portfolio",
        f"{BASE}/employees?period=4w",
    ],
)
def test_основные_отчёты_без_n_plus_1(url: str) -> None:
    plant = make_plant()
    client = client_for(UserFactory.create())
    _orders_with_work(plant, 1)
    with CaptureQueriesContext(connection) as small:
        assert client.get(url).status_code == 200

    _orders_with_work(plant, 4)
    with CaptureQueriesContext(connection) as large:
        assert client.get(url).status_code == 200

    assert len(large.captured_queries) == len(small.captured_queries)
