"""Запись контроля операции (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3) на настоящем
заказе `production`: правила этапа и точки контроля, журнал заказа в той же транзакции,
предупреждение о списании, виза операции без контроля, права API (и разрешение, и
запрет), журнал записей без N+1. Корневой `tests/` — нужны модели обоих модулей."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import FOREMAN, OBSERVER, PRODUCTION_HEAD, QC_ENGINEER
from src.core.accounts.tests.factories import UserFactory
from src.core.org.models import Employee
from src.core.org.tests.factories import EmployeeFactory
from src.production.exceptions import InspectionRequired
from src.production.models import (
    JournalKind,
    Operation,
    OperationStatus,
    OrderJournalEntry,
    OrderStage,
    ProductionOrder,
)
from src.production.services import operation as operation_services
from src.production.tests.factories import WorkCenterFactory
from src.production.tests.support import (
    Plant,
    client_for,
    launch_order,
    make_plant,
    user_with_employee,
)
from src.quality.exceptions import (
    DefectNotClassified,
    InvalidCounts,
    NoInspectionPoint,
    OrderNotLaunched,
    ReferenceNotFound,
)
from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord
from src.quality.services.inspection import InspectionDTO, record_inspection

pytestmark = pytest.mark.django_db

BASE = "/api/v1/quality"


def _point(plant: Plant) -> InspectionPoint:
    point = InspectionPoint.objects.create(
        work_center_id=plant.prod.id, name="Контроль сборки шкафа"
    )
    DefectType.objects.create(inspection_point=point, name="ошибка сборки")
    return point


def _stage(order: ProductionOrder, stage: OrderStage) -> None:
    shipped = timezone.now() if stage == OrderStage.DONE else None
    ProductionOrder.objects.filter(id=order.id).update(stage=stage, shipped_at=shipped)


def _assembly(order: ProductionOrder) -> Operation:
    return Operation.objects.get(order=order, name="Сборка")


def _record(op: Operation, data: InspectionDTO, inspector: Employee | None = None) -> Any:
    return record_inspection(
        op.id,
        data,
        actor_id=UserFactory.create().id,
        inspector_id=(inspector or EmployeeFactory.create()).id,
    )


def _defect(point: InspectionPoint) -> DefectType:
    return point.defect_types.get()


def _cause() -> DefectCause:
    return DefectCause.objects.get(name="Оператор")


def _qc_journal(order: ProductionOrder) -> list[str]:
    return list(
        OrderJournalEntry.objects.filter(order=order, kind=JournalKind.QC).values_list(
            "text", flat=True
        )
    )


def test_запись_контроля_пишет_журнал_заказа_в_той_же_транзакции() -> None:
    plant = make_plant()
    point = _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    op = _assembly(order)
    inspector = EmployeeFactory.create()

    result = _record(
        op,
        InspectionDTO(
            checked=5,
            rework=1,
            scrap=1,
            defect_type_id=_defect(point).id,
            cause_id=_cause().id,
            comment="Перепутаны клеммы",
        ),
        inspector,
    )

    record = InspectionRecord.objects.get(id=result.record_id)
    assert (record.order_id, record.work_center_id, record.inspector_id) == (
        order.id,
        plant.prod.id,
        inspector.id,
    )
    assert result.needs_remake is True
    entry = OrderJournalEntry.objects.get(order=order, kind=JournalKind.QC)
    assert entry.operation_id == op.id
    assert entry.author_id == inspector.id
    assert entry.text == (
        "Контроль сборки шкафа: проверено 5, брак 2 (доработка 1, списание 1) — "
        "ошибка сборки, причина: Оператор. Перепутаны клеммы"
    )


def test_годная_партия_без_замечаний_не_требует_повторного_изготовления() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PREP)

    result = _record(_assembly(order), InspectionDTO(checked=3))

    assert result.needs_remake is False
    assert _qc_journal(order) == ["Контроль сборки шкафа: проверено 3, замечаний нет"]


def test_откат_транзакции_не_оставляет_ни_записи_ни_журнала() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)

    with pytest.raises(RuntimeError), transaction.atomic():
        _record(_assembly(order), InspectionDTO(checked=3))
        raise RuntimeError

    assert not InspectionRecord.objects.exists()
    assert _qc_journal(order) == []


def test_до_запуска_в_производство_контроль_не_пишется() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)  # этап «Запуск»

    with pytest.raises(OrderNotLaunched):
        _record(_assembly(order), InspectionDTO(checked=1))
    _stage(order, OrderStage.DONE)
    with pytest.raises(OrderNotLaunched):
        _record(_assembly(order), InspectionDTO(checked=1))


def test_входной_контроль_снабжения_пишется_уже_на_этапе_запуска() -> None:
    snab = WorkCenterFactory.create(is_supply=True, capacity=0)
    InspectionPoint.objects.create(work_center_id=snab.id, name="Входной контроль")
    plant = make_plant()
    plant.prep = snab
    order = launch_order(plant=plant)

    result = _record(Operation.objects.get(order=order, name="КД"), InspectionDTO(checked=4))

    assert InspectionRecord.objects.filter(id=result.record_id).exists()


def test_у_участка_без_точки_контроля_записи_нет() -> None:
    order = launch_order()
    _stage(order, OrderStage.PROD)

    with pytest.raises(NoInspectionPoint):
        _record(_assembly(order), InspectionDTO(checked=1))


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (InspectionDTO(checked=0), InvalidCounts),
        (InspectionDTO(checked=2, rework=2, scrap=1), InvalidCounts),
        (InspectionDTO(checked=2, rework=1), DefectNotClassified),
    ],
)
def test_неверные_количества_и_неклассифицированный_брак_отклоняются(
    data: InspectionDTO, error: type[Exception]
) -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)

    with pytest.raises(error):
        _record(_assembly(order), data)
    assert not InspectionRecord.objects.exists()


def test_вид_дефекта_чужой_точки_отклоняется_без_следов() -> None:
    plant = make_plant()
    _point(plant)
    other = InspectionPoint.objects.create(work_center_id=plant.qc.id, name="ПСИ")
    foreign = DefectType.objects.create(inspection_point=other, name="функциональный отказ")
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)

    with pytest.raises(ReferenceNotFound):
        _record(
            _assembly(order),
            InspectionDTO(checked=2, scrap=1, defect_type_id=foreign.id, cause_id=_cause().id),
        )
    assert not InspectionRecord.objects.exists()
    assert _qc_journal(order) == []


def test_виза_операции_с_точкой_контроля_требует_записи_контроля() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    now = timezone.now()
    kd = Operation.objects.get(order=order, name="КД")
    Operation.objects.filter(id=kd.id).update(
        status=OperationStatus.DONE,
        progress=100,
        started_at=now,
        approved_at=now,
        approved_by=kd.responsible,
    )
    op = _assembly(order)
    operation_services.set_operation_status(
        op.id, OperationStatus.WORK, actor_id=UserFactory.create().id, actor_employee_id=None
    )

    def approve() -> None:
        operation_services.approve_operation(
            op.id, actor_id=UserFactory.create().id, approver_id=EmployeeFactory.create().id
        )

    with pytest.raises(InspectionRequired):
        approve()
    _record(op, InspectionDTO(checked=1))
    approve()
    assert Operation.objects.get(id=op.id).status == OperationStatus.DONE


# --- API ---------------------------------------------------------------------------


def _post_record(client: Any, op: Operation, data: dict[str, Any]) -> Any:
    return client.post(f"{BASE}/operations/{op.id}/records", data, content_type="application/json")


def test_инженер_отк_записывает_контроль_и_получает_предупреждение_о_списании() -> None:
    plant = make_plant()
    point = _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    user, me = user_with_employee(QC_ENGINEER)
    client = client_for(user)
    op = _assembly(order)

    panel = client.get(f"{BASE}/operations/{op.id}").json()
    assert panel["abilities"] == {"can_record": True}
    assert panel["point"]["name"] == "Контроль сборки шкафа"

    response = _post_record(
        client,
        op,
        {
            "checked": 4,
            "scrap": 2,
            "defect_type_id": str(_defect(point).id),
            "cause_id": str(_cause().id),
        },
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["warning"] == ("Списано 2 шт. — нужно повторное изготовление; учтите в плане.")
    assert body["record"]["inspector_id"] == str(me.id)
    panel = client.get(f"{BASE}/operations/{op.id}").json()
    assert panel["aggregate"] == {
        "checked": 4,
        "rework": 0,
        "scrap": 2,
        "defects": 2,
        "pct": "50.0",
    }


@pytest.mark.parametrize("role", [FOREMAN, QC_ENGINEER])
def test_мастер_и_инженер_отк_вправе_записывать(role: str) -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    user, _ = user_with_employee(role)

    assert _post_record(client_for(user), _assembly(order), {"checked": 1}).status_code == 201


@pytest.mark.parametrize("role", [OBSERVER, PRODUCTION_HEAD])
def test_без_права_контроля_и_не_ответственный_получает_отказ(role: str) -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    user, _ = user_with_employee(role)
    client = client_for(user)
    op = _assembly(order)

    assert client.get(f"{BASE}/operations/{op.id}").json()["abilities"]["can_record"] is False
    assert _post_record(client, op, {"checked": 1}).status_code == 403
    assert not InspectionRecord.objects.exists()


def test_ответственный_за_операцию_записывает_без_роли() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    user, me = user_with_employee()
    op = _assembly(order)
    Operation.objects.filter(id=op.id).update(responsible=me)

    assert _post_record(client_for(user), op, {"checked": 1}).status_code == 201


def test_до_запуска_панель_закрыта_для_записи_и_api_отвечает_409() -> None:
    plant = make_plant()
    _point(plant)
    order = launch_order(plant=plant)
    user, _ = user_with_employee(QC_ENGINEER)
    client = client_for(user)
    op = _assembly(order)

    panel = client.get(f"{BASE}/operations/{op.id}").json()
    assert (panel["recording_open"], panel["abilities"]["can_record"]) == (False, False)
    response = _post_record(client, op, {"checked": 1})
    assert response.status_code == 409
    assert response.json()["code"] == "order_not_launched"


def test_журнал_записей_без_n_плюс_1() -> None:
    plant = make_plant()
    point = _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    user, _ = user_with_employee()
    client = client_for(user)

    def count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"{BASE}/records")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    _record(_assembly(order), InspectionDTO(checked=1))
    one = count()
    for _ in range(5):
        other = launch_order(plant=plant)
        _stage(other, OrderStage.PROD)
        _record(
            _assembly(other),
            InspectionDTO(
                checked=2, rework=1, defect_type_id=_defect(point).id, cause_id=_cause().id
            ),
        )
    rows = client.get(f"{BASE}/records").json()

    assert len(rows) == 6
    assert {row["order_number"] for row in rows} >= {order.number}
    assert {row["operation_name"] for row in rows} == {"20. Сборка"}
    assert count() == one


def test_сводка_качества_читается_любым_и_считает_kpi() -> None:
    plant = make_plant()
    point = _point(plant)
    order = launch_order(plant=plant)
    _stage(order, OrderStage.PROD)
    _record(
        _assembly(order),
        InspectionDTO(checked=10, rework=2, defect_type_id=_defect(point).id, cause_id=_cause().id),
    )
    user, _ = user_with_employee(OBSERVER)

    body = client_for(user).get(f"{BASE}/summary?weeks=4").json()

    assert body["kpi"]["checked"] == 10
    assert body["kpi"]["defects"] == 2
    assert body["kpi"]["pct"] == "20.0"
    assert body["kpi"]["operator_pct"] == "100.0"
    assert body["kpi"]["early_pct"] == "100.0"
    assert len(body["dynamics"]) == 12
    assert body["pareto_causes"][0]["name"] == "Оператор"
    (row,) = body["by_work_center"]
    assert (row["point_name"], row["checked"], row["top_defect"]["name"]) == (
        "Контроль сборки шкафа",
        10,
        "ошибка сборки",
    )
