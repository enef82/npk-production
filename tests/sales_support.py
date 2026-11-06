"""Построители тестов, которым нужны модели и `sales`, и `production` (модулю нельзя
импортировать чужие модели даже в тестах — поэтому корневой `tests/`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from src.core.accounts.tests.factories import UserFactory
from src.core.identity.tests.factories import PartyFactory
from src.core.org.models import Employee
from src.core.org.tests.factories import EmployeeFactory
from src.production.models import (
    ProductTemplate,
    TemplateMaterial,
    TemplateOperationDependency,
    WorkCenter,
    WorkPhase,
)
from src.production.tests.factories import (
    ProductTemplateFactory,
    TemplateOperationFactory,
    WorkCenterFactory,
)
from src.sales.models import Inquiry, SalesSettings
from src.sales.services import inquiry as inquiry_services


@dataclass
class Shop:
    kb: WorkCenter
    snab: WorkCenter
    sb: WorkCenter
    template: ProductTemplate
    economist: Employee


def make_shop() -> Shop:
    """Шаблон «КД (24 ч) → Закупка (15 дн) → Сборка (16 ч × кол-во, 2 чел.)»."""

    kb = WorkCenterFactory.create(
        phase=WorkPhase.PREP,
        hourly_rate=Decimal("1800"),
        capacity=1,
        responsible=EmployeeFactory.create(),
    )
    snab = WorkCenterFactory.create(
        phase=WorkPhase.PREP,
        hourly_rate=Decimal("0"),
        capacity=0,
        is_supply=True,
        responsible=EmployeeFactory.create(),
    )
    sb = WorkCenterFactory.create(
        phase=WorkPhase.PROD,
        hourly_rate=Decimal("1300"),
        capacity=2,
        responsible=EmployeeFactory.create(),
    )
    template = ProductTemplateFactory.create(code="ШУ", name="Шкаф управления АСУ ТП")
    TemplateMaterial.objects.create(
        template=template, name="Корпус", qty_per_unit=Decimal("1"), price=Decimal("68000")
    )
    kd = TemplateOperationFactory.create(
        template=template, seq=10, name="КД", work_center=kb, hours=Decimal("24")
    )
    buy = TemplateOperationFactory.create(
        template=template, seq=20, name="Закупка", work_center=snab, hours=Decimal("15")
    )
    build = TemplateOperationFactory.create(
        template=template,
        seq=30,
        name="Сборка",
        work_center=sb,
        hours=Decimal("16"),
        scales_with_qty=True,
        people=2,
    )
    TemplateOperationDependency.objects.create(predecessor=kd, successor=buy)
    TemplateOperationDependency.objects.create(predecessor=buy, successor=build)
    economist = EmployeeFactory.create()
    settings, _ = SalesSettings.objects.get_or_create()
    settings.economist = economist
    settings.save()
    return Shop(kb=kb, snab=snab, sb=sb, template=template, economist=economist)


def make_inquiry(shop: Shop, *, manager: Employee | None = None, quantity: str = "2") -> Inquiry:
    inquiry_id = inquiry_services.create_inquiry(
        inquiry_services.InquiryCreateDTO(
            customer_id=PartyFactory.create().id,
            object_name="Насосная станция",
            template_id=shop.template.id,
            quantity=Decimal(quantity),
            due_date=timezone.localdate() + timedelta(days=120),
            manager_id=(manager or EmployeeFactory.create()).id,
        ),
        actor_id=UserFactory.create().id,
    )
    return Inquiry.objects.get(id=inquiry_id)
