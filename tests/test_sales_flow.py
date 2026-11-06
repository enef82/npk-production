"""Заявка от регистрации до запуска (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2):
калькуляция из шаблона, план, этапы с визами (включая запрещённые переходы), запуск в
одной транзакции с созданием производственного заказа, проигрыш."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from src.core.accounts.tests.factories import UserFactory
from src.core.common.scheduling import add_working_days
from src.core.events.models import OutboxEvent
from src.core.identity.models import Party
from src.core.identity.services.dedup import DuplicatesFound
from src.core.org.tests.factories import EmployeeFactory
from src.production.exceptions import WorkCenterNotFound
from src.production.models import Operation, OperationDependency, ProductionOrder
from src.production.services.common import fmt_date
from src.sales.calculations import calc_totals
from src.sales.exceptions import (
    InquiryClosed,
    ReasonRequired,
    StageRequirementsNotMet,
    StageSkip,
    VisaRequired,
)
from src.sales.models import (
    CalcMaterial,
    CalcOperation,
    CalcOperationDependency,
    Inquiry,
    InquiryStage,
    InquiryStageApproval,
)
from src.sales.planning import centers_by_id
from src.sales.selectors import lines_for_totals
from src.sales.services import calculation as calc
from src.sales.services import inquiry as services
from src.sales.tests.factories import LossReasonFactory
from tests.sales_support import Shop, make_inquiry, make_shop

pytestmark = pytest.mark.django_db


def _move(inquiry: Inquiry, to: InquiryStage, **kwargs: object) -> None:
    services.move_inquiry_stage(
        inquiry.id,
        to,
        actor_id=UserFactory.create().id,
        actor_employee_id=kwargs.pop("employee_id", None),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _reload(inquiry: Inquiry) -> Inquiry:
    return Inquiry.objects.get(id=inquiry.id)


def _ready_for_launch(shop: Shop) -> Inquiry:
    inquiry = make_inquiry(shop)
    calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)
    calc.build_plan(
        inquiry.id, add_working_days(timezone.localdate(), 5), actor_id=UserFactory.create().id
    )
    _move(inquiry, InquiryStage.CALC, employee_id=inquiry.manager_id, may_approve=True)
    _move(inquiry, InquiryStage.APPROVAL, employee_id=shop.economist.id, may_approve=True)
    return _reload(inquiry)


def test_заявка_с_новым_заказчиком_заводит_контрагента_и_визы() -> None:
    shop = make_shop()
    manager = EmployeeFactory.create()
    inquiry_id = services.create_inquiry(
        services.InquiryCreateDTO(
            new_customer=services.NewCustomer(short_name="АО «Уралхимпласт»", inn="6623000001"),
            object_name="Насосная",
            quantity=Decimal("2"),
            due_date=timezone.localdate(),
            manager_id=manager.id,
        ),
        actor_id=UserFactory.create().id,
    )
    inquiry = Inquiry.objects.get(id=inquiry_id)
    assert Party.objects.get(id=inquiry.customer_id).short_name == "АО «Уралхимпласт»"
    assert inquiry.number.startswith("З-")
    responsibles = dict(
        InquiryStageApproval.objects.filter(inquiry=inquiry).values_list("stage", "responsible_id")
    )
    assert responsibles == {
        InquiryStage.NEW: manager.id,
        InquiryStage.CALC: shop.economist.id,
        InquiryStage.APPROVAL: manager.id,
    }

    with pytest.raises(DuplicatesFound):
        services.create_inquiry(
            services.InquiryCreateDTO(
                new_customer=services.NewCustomer(short_name="Уралхимпласт", inn="6623000001"),
                object_name="Насосная 2",
                quantity=Decimal("1"),
                due_date=timezone.localdate(),
                manager_id=manager.id,
            ),
            actor_id=UserFactory.create().id,
        )


def test_заполнение_из_шаблона_умножает_количество_и_копирует_связи() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop, quantity="3")
    calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)

    [material] = CalcMaterial.objects.filter(inquiry=inquiry)
    assert material.quantity == Decimal("3.000")
    ops = {op.name: op for op in CalcOperation.objects.filter(inquiry=inquiry)}
    assert ops["КД"].hours == Decimal("24")  # не зависит от количества
    assert ops["Сборка"].hours == Decimal("48.00")
    assert ops["Сборка"].people == 2
    assert set(
        CalcOperationDependency.objects.filter(successor__inquiry=inquiry).values_list(
            "predecessor__name", "successor__name"
        )
    ) == {("КД", "Закупка"), ("Закупка", "Сборка")}


def test_итог_заявки_считается_по_ставкам_участков() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop, quantity="2")
    calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)
    materials, labor = lines_for_totals(
        CalcMaterial.objects.filter(inquiry=inquiry),
        CalcOperation.objects.filter(inquiry=inquiry),
        centers_by_id(),
    )
    totals = calc_totals(
        materials, labor, overhead_pct=Decimal(25), margin_pct=Decimal(20), vat_pct=Decimal(22)
    )
    # мат 136000; труд 24 × 1800 + 32 × 1300 = 84800; снабжение — 0
    assert totals.materials == Decimal("136000.0000")
    assert totals.labor == Decimal("84800.0000")
    assert totals.hours == Decimal("56.0000")


def test_план_заявки_прямым_проходом_со_снабжением_в_днях() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop, quantity="1")
    calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)
    start = add_working_days(timezone.localdate(), 10)
    calc.build_plan(inquiry.id, start, actor_id=UserFactory.create().id)
    ops = {op.name: op for op in CalcOperation.objects.filter(inquiry=inquiry)}
    assert ops["КД"].planned_start == start
    assert ops["Закупка"].planned_start == add_working_days(start, 3)  # 24 ч → 3 дня
    assert ops["Сборка"].planned_start == add_working_days(start, 18)  # + 15 дней поставки


def test_вперёд_без_визы_нельзя_а_ответственный_визирует_переходом() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop)
    with pytest.raises(VisaRequired):
        _move(inquiry, InquiryStage.CALC)
    _move(inquiry, InquiryStage.CALC, employee_id=inquiry.manager_id, may_approve=True)
    assert _reload(inquiry).stage == InquiryStage.CALC


def test_на_согласование_только_с_калькуляцией_и_планом() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop)
    _move(inquiry, InquiryStage.CALC, employee_id=inquiry.manager_id, may_approve=True)
    with pytest.raises(StageRequirementsNotMet, match="Нет калькуляции"):
        _move(inquiry, InquiryStage.APPROVAL, employee_id=shop.economist.id, may_approve=True)
    calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)
    with pytest.raises(StageRequirementsNotMet, match="Нет плана"):
        _move(inquiry, InquiryStage.APPROVAL, employee_id=shop.economist.id, may_approve=True)
    calc.build_plan(inquiry.id, None, actor_id=UserFactory.create().id)
    _move(inquiry, InquiryStage.APPROVAL, employee_id=shop.economist.id, may_approve=True)
    assert _reload(inquiry).stage == InquiryStage.APPROVAL


def test_перескок_и_возврат_без_причины_запрещены() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop)
    with pytest.raises(StageSkip):
        _move(inquiry, InquiryStage.APPROVAL, employee_id=inquiry.manager_id, may_approve=True)
    with pytest.raises(StageSkip):
        _move(inquiry, InquiryStage.LAUNCHED)
    _move(inquiry, InquiryStage.CALC, employee_id=inquiry.manager_id, may_approve=True)
    with pytest.raises(ReasonRequired):
        _move(inquiry, InquiryStage.NEW)
    _move(inquiry, InquiryStage.NEW, comment="Заказчик уточняет ТЗ")
    assert (
        InquiryStageApproval.objects.get(inquiry=inquiry, stage=InquiryStage.NEW).approved_at
        is None
    )


def test_запуск_создаёт_заказ_в_той_же_транзакции_и_оба_события() -> None:
    shop = make_shop()
    inquiry = _ready_for_launch(shop)
    start = add_working_days(timezone.localdate(), 7)
    due = timezone.localdate() + timedelta(days=100)

    result = services.launch_inquiry(
        inquiry.id,
        planned_start=start,
        due_date=due,
        actor_id=UserFactory.create().id,
        actor_employee_id=inquiry.manager_id,
        may_approve=True,
    )

    inquiry = _reload(inquiry)
    assert inquiry.stage == InquiryStage.LAUNCHED
    assert inquiry.order_id == result.order_id
    order = ProductionOrder.objects.get(id=result.order_id)
    assert order.inquiry_id == inquiry.id
    assert order.due_date == due
    assert order.planned_start == start
    assert order.customer_id == inquiry.customer_id
    materials, labor = lines_for_totals(
        CalcMaterial.objects.filter(inquiry=inquiry),
        CalcOperation.objects.filter(inquiry=inquiry),
        centers_by_id(),
    )
    totals = calc_totals(
        materials, labor, overhead_pct=Decimal(25), margin_pct=Decimal(20), vat_pct=Decimal(22)
    )
    assert order.contract_total == totals.total
    assert order.labor_cost_planned == totals.labor
    assert Operation.objects.filter(order=order).count() == 3
    assert OperationDependency.objects.filter(successor__order=order).count() == 2
    assert OutboxEvent.objects.filter(
        event_type="sales.inquiry_launched", aggregate_id=inquiry.id
    ).exists()
    assert OutboxEvent.objects.filter(
        event_type="production.order_launched", aggregate_id=order.id
    ).exists()
    assert result.warnings  # КД ещё нет
    assert fmt_date(start) in order.journal.get().text


def test_запуск_без_участка_ничего_не_оставляет() -> None:
    shop = make_shop()
    inquiry = _ready_for_launch(shop)
    CalcOperation.objects.filter(inquiry=inquiry, name="Сборка").update(
        work_center_id=uuid4()  # не участок
    )
    with pytest.raises(WorkCenterNotFound):
        services.launch_inquiry(
            inquiry.id,
            planned_start=timezone.localdate(),
            due_date=timezone.localdate(),
            actor_id=UserFactory.create().id,
            actor_employee_id=inquiry.manager_id,
            may_approve=True,
        )
    assert _reload(inquiry).stage == InquiryStage.APPROVAL
    assert not ProductionOrder.objects.exists()
    assert not OutboxEvent.objects.filter(event_type="sales.inquiry_launched").exists()


def test_откат_внешней_транзакции_отменяет_и_заказ_и_события() -> None:
    shop = make_shop()
    inquiry = _ready_for_launch(shop)

    class Boom(Exception):
        pass

    with pytest.raises(Boom), transaction.atomic():
        services.launch_inquiry(
            inquiry.id,
            planned_start=timezone.localdate(),
            due_date=timezone.localdate(),
            actor_id=UserFactory.create().id,
            actor_employee_id=inquiry.manager_id,
            may_approve=True,
        )
        raise Boom

    assert not ProductionOrder.objects.exists()
    assert not OutboxEvent.objects.filter(
        event_type__in=["sales.inquiry_launched", "production.order_launched"]
    ).exists()


def test_запуск_без_визы_согласования_запрещён() -> None:
    shop = make_shop()
    inquiry = _ready_for_launch(shop)
    with pytest.raises(VisaRequired):
        services.launch_inquiry(
            inquiry.id,
            planned_start=timezone.localdate(),
            due_date=timezone.localdate(),
            actor_id=UserFactory.create().id,
            actor_employee_id=None,
        )


def test_проигрыш_с_причиной_закрывает_правку() -> None:
    shop = make_shop()
    inquiry = make_inquiry(shop)
    reason = LossReasonFactory.create(name="Цена")
    services.lose_inquiry(inquiry.id, reason.id, "Дорого", actor_id=UserFactory.create().id)
    inquiry = _reload(inquiry)
    assert inquiry.stage == InquiryStage.LOST
    assert inquiry.lost_reason_id == reason.id
    with pytest.raises(InquiryClosed):
        calc.fill_from_template(inquiry.id, None, actor_id=UserFactory.create().id)
    with pytest.raises(InquiryClosed):
        services.lose_inquiry(inquiry.id, reason.id, "", actor_id=UserFactory.create().id)
