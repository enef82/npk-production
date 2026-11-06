"""Снабжение на настоящих заказах `production` и заявках `sales`
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4): потребность по событию
`production.order_launched` (и её идемпотентность), переходы строк — разрешённые и
запрещённые, журнал заказа и история строки в той же транзакции, заявки «на склад / ТО»,
права по ролям в API (и разрешение, и запрет), реестр без N+1. Корневой `tests/` — нужны
модели нескольких модулей."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import (
    OBSERVER,
    PROCUREMENT_OFFICER,
    PRODUCTION_HEAD,
    PROJECT_MANAGER,
    WAREHOUSE_HEAD,
)
from src.core.accounts.tests.factories import UserFactory
from src.core.common.scheduling import add_working_days
from src.core.events.models import OutboxEvent
from src.core.events.services.dispatch import dispatch_batch
from src.core.org.tests.factories import EmployeeFactory
from src.production.models import (
    JournalKind,
    Operation,
    OrderJournalEntry,
    OrderStage,
    ProductionOrder,
)
from src.production.planning import finish_of
from src.production.tests.support import client_for, launch_order, user_with_employee
from src.sales.models import Inquiry, InquiryStage
from src.sales.services import calculation as calc
from src.sales.services import inquiry as inquiry_services
from src.supply import facade
from src.supply.exceptions import (
    InvalidTransition,
    MixedOrders,
    OperationMismatch,
    OrderClosed,
    ReasonRequired,
    SupplierRequired,
)
from src.supply.handlers import create_order_demand
from src.supply.models import (
    LineCategory,
    LineKind,
    LineStatus,
    PurchaseLine,
    PurchaseLineHistory,
    Supplier,
    ToolTemplate,
)
from src.supply.services import lines as services
from src.supply.services.lines import LineDTO
from tests.sales_support import make_inquiry, make_shop

pytestmark = pytest.mark.django_db

BASE = "/api/v1/supply"


def _actor() -> dict[str, Any]:
    return {"actor_id": UserFactory.create().id, "author_id": EmployeeFactory.create().id}


def _dto(name: str = "Кабель ВВГнг 3×2,5", **kwargs: Any) -> LineDTO:
    values: dict[str, Any] = {
        "kind": LineKind.MATERIAL,
        "category": LineCategory.MATERIAL,
        "name": name,
        "quantity": Decimal("100"),
        "unit": "м",
        "price": Decimal("85"),
        "need_date": timezone.localdate() + timedelta(days=10),
    }
    values.update(kwargs)
    return LineDTO(**values)


def _draft(order: ProductionOrder | None, name: str = "Кабель ВВГнг 3×2,5") -> PurchaseLine:
    line_id = services.create_line(order.id if order else None, _dto(name), **_actor())
    return PurchaseLine.objects.get(id=line_id)


def _reload(line: PurchaseLine) -> PurchaseLine:
    return PurchaseLine.objects.get(id=line.id)


def _proc_journal(order: ProductionOrder) -> list[str]:
    return list(
        OrderJournalEntry.objects.filter(order=order, kind=JournalKind.PROC)
        .order_by("created_at")
        .values_list("text", flat=True)
    )


def _ordered(line: PurchaseLine, eta_days: int = 5) -> PurchaseLine:
    if _reload(line).status == LineStatus.DRAFT:
        services.send_lines([line.id], **_actor())
    services.place_order(
        [line.id],
        supplier_id=Supplier.objects.get_or_create(name="ООО «Уралметаллсервис»")[0].id,
        eta=timezone.localdate() + timedelta(days=eta_days),
        **_actor(),
    )
    return _reload(line)


# --- Потребность по запуску заказа ------------------------------------------------


def _launched_inquiry() -> Inquiry:
    shop = make_shop()
    ToolTemplate.objects.create(
        work_center_id=shop.sb.id,
        category=LineCategory.CONSUMABLE,
        name="Стяжки, маркировка",
        quantity=Decimal("1"),
        unit="компл",
        price=Decimal("1200"),
    )
    ToolTemplate.objects.create(
        work_center_id=shop.sb.id,
        category=LineCategory.TOOL,
        name="Кримпер для НШВИ",
        quantity=Decimal("1"),
        unit="шт",
        price=Decimal("4200"),
    )
    inquiry = make_inquiry(shop, quantity="6")
    actor = UserFactory.create().id
    calc.fill_from_template(inquiry.id, None, actor_id=actor)
    calc.build_plan(inquiry.id, add_working_days(timezone.localdate(), 5), actor_id=actor)

    def move(to: InquiryStage, employee: UUID) -> None:
        inquiry_services.move_inquiry_stage(
            inquiry.id, to, actor_id=actor, actor_employee_id=employee, may_approve=True
        )

    move(InquiryStage.CALC, inquiry.manager_id)
    move(InquiryStage.APPROVAL, shop.economist.id)
    inquiry_services.launch_inquiry(
        inquiry.id,
        planned_start=add_working_days(timezone.localdate(), 5),
        due_date=timezone.localdate() + timedelta(days=120),
        actor_id=actor,
        actor_employee_id=inquiry.manager_id,
        may_approve=True,
    )
    return Inquiry.objects.get(id=inquiry.id)


def test_запуск_заказа_порождает_черновики_материалов_и_оснастки() -> None:
    inquiry = _launched_inquiry()
    assert inquiry.order_id is not None

    dispatch_batch()

    order = ProductionOrder.objects.get(id=inquiry.order_id)
    buy = Operation.objects.select_related("work_center").get(order=order, name="Закупка")
    build = Operation.objects.get(order=order, name="Сборка")
    material = PurchaseLine.objects.get(order_id=order.id, kind=LineKind.MATERIAL)
    assert (material.name, material.quantity, material.price, material.status) == (
        "Корпус",
        Decimal("6.000"),
        Decimal("68000.0000"),
        LineStatus.DRAFT,
    )
    assert material.operation_id == buy.id
    assert material.need_date == finish_of(buy)
    assert material.created_by_id is None
    tools = {
        line.name: line
        for line in PurchaseLine.objects.filter(order_id=order.id, kind=LineKind.TOOL)
    }
    # Расходники — на каждые 5 изделий: 6 шт. → ×2; инструмент — на заказ.
    assert tools["Стяжки, маркировка"].quantity == Decimal("2.000")
    assert tools["Кримпер для НШВИ"].quantity == Decimal("1.000")
    assert build.planned_start is not None
    assert tools["Кримпер для НШВИ"].need_date == add_working_days(build.planned_start, -2)
    assert _proc_journal(order) == [
        "Потребность в материалах: добавлено 1 поз.",
        "Оснастка и расходники по маршруту: добавлено 2 поз.",
    ]
    assert OutboxEvent.objects.get(event_type="production.order_launched").processed_at


def test_повторная_доставка_события_не_удваивает_потребность() -> None:
    inquiry = _launched_inquiry()
    event = OutboxEvent.objects.get(event_type="production.order_launched")

    create_order_demand(event)
    create_order_demand(event)

    assert inquiry.order_id is not None
    assert PurchaseLine.objects.filter(order_id=inquiry.order_id).count() == 3
    order = ProductionOrder.objects.get(id=inquiry.order_id)
    assert len(_proc_journal(order)) == 2


def test_добавить_из_калькуляции_добавляет_только_недостающее() -> None:
    inquiry = _launched_inquiry()
    dispatch_batch()
    order_id = inquiry.order_id
    assert order_id is not None
    PurchaseLine.objects.filter(order_id=order_id, kind=LineKind.TOOL).first().delete()  # type: ignore[union-attr]

    assert services.fill_order_lines(order_id, LineKind.MATERIAL, **_actor()) == 0
    assert services.fill_order_lines(order_id, LineKind.TOOL, **_actor()) == 1
    assert PurchaseLine.objects.filter(order_id=order_id).count() == 3


# --- Переходы ---------------------------------------------------------------------


def test_передача_в_закупку_даёт_общий_номер_заявки_и_пишет_журнал() -> None:
    order = launch_order()
    first, second = _draft(order, "Корпус"), _draft(order, "Автомат 16 А")
    author = EmployeeFactory.create()

    number = services.send_lines(
        [first.id, second.id], actor_id=UserFactory.create().id, author_id=author.id
    )

    year = timezone.localdate().year
    assert number.startswith(f"ЗЗ-{year}-")
    for line in (first, second):
        line = _reload(line)
        assert (line.status, line.requisition_no, line.sent_by_id) == (
            LineStatus.SENT,
            number,
            author.id,
        )
        assert line.sent_at is not None
    assert _proc_journal(order) == [
        f"«Корпус»: Заявка {number} передана в закупку",
        f"«Автомат 16 А»: Заявка {number} передана в закупку",
    ]
    assert OrderJournalEntry.objects.filter(kind=JournalKind.PROC, author=author).count() == 2


def test_в_одну_заявку_нельзя_смешать_разные_заказы() -> None:
    first, second = _draft(launch_order()), _draft(launch_order())

    with pytest.raises(MixedOrders):
        services.send_lines([first.id, second.id], **_actor())
    assert _reload(first).status == LineStatus.DRAFT


def test_полный_путь_строки_заказ_приёмка_выдача_с_историей() -> None:
    order = launch_order()
    line = _draft(order, "Корпус")
    services.send_lines([line.id], **_actor())
    supplier = Supplier.objects.create(name="ООО «ЭлектроКомплект-Урал»")
    eta = timezone.localdate() + timedelta(days=15)

    po = services.place_order([line.id], supplier_id=supplier.id, eta=eta, **_actor())
    line = _reload(line)
    assert po.startswith(f"ЗП-{timezone.localdate().year}-")
    assert (line.status, line.supplier_id, line.po_number, line.eta) == (
        LineStatus.ORDERED,
        supplier.id,
        po,
        eta,
    )

    services.receive_lines(
        [line.id],
        received_at=timezone.localdate(),
        storage_place="Склад №2",
        received_qty=Decimal("60"),
        nonconforming=Decimal("1"),
        **_actor(),
    )
    line = _reload(line)
    assert (line.status, line.received_qty, line.storage_place) == (
        LineStatus.RECEIVED,
        Decimal("60.000"),
        "Склад №2",
    )

    recipient = EmployeeFactory.create(full_name="Гусев И.Д.")
    services.issue_lines(
        [line.id],
        issued_at=timezone.localdate(),
        issued_to_id=recipient.id,
        work_center_name="Сборка шкафов",
        **_actor(),
    )
    line = _reload(line)
    assert (line.status, line.issued_to_id) == (LineStatus.ISSUED, recipient.id)

    journal = _proc_journal(order)
    assert journal[1] == (
        f"«Корпус»: Заказано у ООО «ЭлектроКомплект-Урал», {po}, срок поставки "
        f"{eta.strftime('%d.%m.%Y')} — позже потребности на 5 дн."
    )
    assert journal[2] == (
        "«Корпус»: Принято на склад (Склад №2): 60 м из 100 — недопоставка, "
        "входной контроль: не соответствует 1"
    )
    assert journal[3] == ("«Корпус»: Передано в производство: Сборка шкафов, получил Гусев И.Д.")
    assert PurchaseLineHistory.objects.filter(line=line).count() == 5


def test_резерв_со_склада_без_закупки_и_выдача() -> None:
    line = _draft(None)
    services.send_lines([line.id], **_actor())

    services.reserve_lines([line.id], **_actor())
    line = _reload(line)
    assert (line.status, line.storage_place, line.received_at) == (
        LineStatus.RESERVED,
        "Склад №1",
        timezone.localdate(),
    )
    services.issue_lines(
        [line.id],
        issued_at=timezone.localdate(),
        issued_to_id=EmployeeFactory.create().id,
        **_actor(),
    )
    assert _reload(line).status == LineStatus.ISSUED


def test_запрещённые_переходы_строки() -> None:
    line = _draft(launch_order())
    issued_to = EmployeeFactory.create().id
    today = timezone.localdate()

    with pytest.raises(InvalidTransition):
        services.receive_lines([line.id], received_at=today, storage_place="", **_actor())
    services.send_lines([line.id], **_actor())
    with pytest.raises(InvalidTransition):
        services.send_lines([line.id], **_actor())
    with pytest.raises(InvalidTransition):
        services.issue_lines([line.id], issued_at=today, issued_to_id=issued_to, **_actor())
    with pytest.raises(InvalidTransition):
        services.update_line(line.id, _dto("Новое имя"), actor_id=UserFactory.create().id)
    line = _ordered(line)
    with pytest.raises(InvalidTransition):
        services.reserve_lines([line.id], **_actor())
    with pytest.raises(InvalidTransition):
        services.delete_line(line.id, actor_id=UserFactory.create().id)
    assert _reload(line).status == LineStatus.ORDERED


def test_групповое_действие_атомарно() -> None:
    order = launch_order()
    good, bad = _draft(order, "Корпус"), _draft(order, "Замки")
    services.send_lines([good.id], **_actor())
    journal_before = _proc_journal(order)

    with pytest.raises(InvalidTransition):
        services.place_order(
            [good.id, bad.id],
            supplier_id=Supplier.objects.create(name="ООО «Альфа»").id,
            eta=timezone.localdate(),
            **_actor(),
        )

    assert _reload(good).status == LineStatus.SENT
    assert _proc_journal(order) == journal_before


def test_заказ_требует_поставщика_а_перенос_срока_причину() -> None:
    line = _draft(None)
    services.send_lines([line.id], **_actor())
    inactive = Supplier.objects.create(name="ООО «Закрыто»", is_active=False)

    with pytest.raises(SupplierRequired):
        services.place_order(
            [line.id], supplier_id=inactive.id, eta=timezone.localdate(), **_actor()
        )
    line = _ordered(line)
    with pytest.raises(ReasonRequired):
        services.change_eta([line.id], eta=timezone.localdate(), reason=" ", **_actor())
    new_eta = timezone.localdate() + timedelta(days=30)
    services.change_eta([line.id], eta=new_eta, reason="письмо поставщика", **_actor())
    assert _reload(line).eta == new_eta


def test_откат_транзакции_снимает_и_строку_и_журнал() -> None:
    order = launch_order()
    line = _draft(order)

    with pytest.raises(RuntimeError), transaction.atomic():
        services.send_lines([line.id], **_actor())
        raise RuntimeError

    assert _reload(line).status == LineStatus.DRAFT
    assert _proc_journal(order) == []


def test_заявка_на_склад_без_заказа_не_пишет_журнал() -> None:
    number = services.create_requisition(
        None,
        [
            _dto("Фильтр чиллера", kind=LineKind.TOOL, category=LineCategory.CONSUMABLE),
            _dto("Масло компрессорное", kind=LineKind.TOOL, category=LineCategory.CONSUMABLE),
        ],
        **_actor(),
    )

    lines = PurchaseLine.objects.filter(requisition_no=number)
    assert {(line.status, line.order_id) for line in lines} == {(LineStatus.SENT, None)}
    assert not OrderJournalEntry.objects.filter(kind=JournalKind.PROC).exists()


def test_операция_строки_должна_быть_из_её_заказа_а_отгруженный_заказ_закрыт() -> None:
    order, other = launch_order(), launch_order()
    foreign_op = Operation.objects.filter(order=other).first()
    assert foreign_op is not None

    with pytest.raises(OperationMismatch):
        services.create_line(order.id, _dto(operation_id=foreign_op.id), **_actor())
    ProductionOrder.objects.filter(id=order.id).update(
        stage=OrderStage.DONE, shipped_at=timezone.now()
    )
    with pytest.raises(OrderClosed):
        services.create_line(order.id, _dto(), **_actor())


def test_фасад_статус_потребности_заказа_и_строки_по_операции() -> None:
    order = launch_order()
    op = Operation.objects.filter(order=order).first()
    assert op is not None
    services.create_line(
        order.id,
        _dto(operation_id=op.id, need_date=timezone.localdate() - timedelta(days=3)),
        **_actor(),
    )
    _ordered(_draft(order, "Корпус"), eta_days=1)

    status = facade.get_order_supply_status(order.id)
    by_op = facade.list_lines_by_operation([op.id])

    assert (status.draft, status.ordered, status.late) == (1, 1, 1)
    assert status.active_amount == Decimal("8500.0000000")
    assert [(b.name, b.late_days) for b in by_op[op.id]] == [("Кабель ВВГнг 3×2,5", 3)]


# --- API ---------------------------------------------------------------------------


def _post(client: Any, url: str, data: dict[str, Any]) -> Any:
    return client.post(url, data, content_type="application/json")


def test_менеджер_передаёт_в_закупку_наблюдатель_нет() -> None:
    order = launch_order()
    line = _draft(order)
    observer, _ = user_with_employee(OBSERVER)
    manager, _ = user_with_employee(PROJECT_MANAGER)

    assert (
        _post(client_for(observer), f"{BASE}/lines/send", {"line_ids": [str(line.id)]}).status_code
        == 403
    )
    tab = client_for(observer).get(f"{BASE}/orders/{order.id}/lines?kind=mat").json()
    assert tab["lines"][0]["abilities"]["can_send"] is False

    tab = client_for(manager).get(f"{BASE}/orders/{order.id}/lines?kind=mat").json()
    assert tab["lines"][0]["abilities"]["can_send"] is True
    response = _post(client_for(manager), f"{BASE}/lines/send", {"line_ids": [str(line.id)]})
    assert response.status_code == 200
    assert _reload(line).status == LineStatus.SENT


@pytest.mark.parametrize(
    ("role", "allowed"), [(PROCUREMENT_OFFICER, True), (WAREHOUSE_HEAD, False)]
)
def test_заказ_поставщику_только_снабжение(role: str, allowed: bool) -> None:
    line = _draft(None)
    services.send_lines([line.id], **_actor())
    user, _ = user_with_employee(role)
    supplier = Supplier.objects.create(name="ООО «Альфа»")

    response = _post(
        client_for(user),
        f"{BASE}/lines/order",
        {
            "line_ids": [str(line.id)],
            "supplier_id": str(supplier.id),
            "eta": str(timezone.localdate()),
            "po_number": "Счёт 17",
        },
    )

    assert response.status_code == (200 if allowed else 403)
    assert _reload(line).status == (LineStatus.ORDERED if allowed else LineStatus.SENT)


@pytest.mark.parametrize(
    ("role", "allowed"),
    [(WAREHOUSE_HEAD, True), (PRODUCTION_HEAD, True), (PROCUREMENT_OFFICER, False)],
)
def test_приёмка_только_склад_и_начальник_производства(role: str, allowed: bool) -> None:
    line = _ordered(_draft(None))
    user, _ = user_with_employee(role)

    response = _post(
        client_for(user),
        f"{BASE}/lines/receive",
        {"line_ids": [str(line.id)], "received_at": str(timezone.localdate())},
    )

    assert response.status_code == (200 if allowed else 403)
    assert _reload(line).status == (LineStatus.RECEIVED if allowed else LineStatus.ORDERED)


def test_новая_заявка_на_склад_через_api_и_история_строки() -> None:
    user, _ = user_with_employee(PRODUCTION_HEAD)
    client = client_for(user)

    response = _post(
        client,
        f"{BASE}/requisitions",
        {
            "order_id": None,
            "lines": [
                {
                    "kind": "tool",
                    "category": "consumable",
                    "name": "Фильтр чиллера",
                    "quantity": "2",
                    "unit": "шт",
                    "price": "4800",
                    "need_date": str(timezone.localdate()),
                }
            ],
        },
    )

    assert response.status_code == 201
    number = response.json()["requisition_no"]
    rows = client.get(f"{BASE}/lines?warehouse_only=true").json()
    assert [(r["requisition_no"], r["status"], r["order_number"]) for r in rows] == [
        (number, "sent", "")
    ]
    detail = client.get(f"{BASE}/lines/{rows[0]['id']}").json()
    assert detail["history"][0]["text"] == f"Заявка {number} передана в закупку"
    dashboard = client.get(f"{BASE}/dashboard").json()
    assert dashboard["requisitions"][0]["number"] == number
    assert dashboard["counts"]["sent"] == 1


def test_реестр_строк_без_n_плюс_1() -> None:
    user, _ = user_with_employee(PROCUREMENT_OFFICER)
    client = client_for(user)

    def count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"{BASE}/lines?status=")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    _ordered(_draft(launch_order()))
    one = count()
    for _ in range(4):
        _ordered(_draft(launch_order()))
    rows = client.get(f"{BASE}/lines?status=").json()

    assert len(rows) == 5
    assert all(r["order_number"] and r["supplier_name"] for r in rows)
    assert count() == one


def test_фильтр_опаздывающих() -> None:
    late = _ordered(_draft(None, "Поздняя"), eta_days=30)
    _ordered(_draft(None, "В срок"), eta_days=1)
    user, _ = user_with_employee()

    rows = client_for(user).get(f"{BASE}/lines?late_only=true").json()

    assert [(r["id"], r["late_days"]) for r in rows] == [(str(late.id), 20)]
