"""Ограничения БД модуля «Снабжение и склад»: попытка нарушить → `IntegrityError`
(CLAUDE.md §8). Статус ставится в конструкторе — так же, как это делает демо-посев."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from src.core.org.tests.factories import EmployeeFactory
from src.supply.models import LineCategory, LineKind, LineStatus
from src.supply.tests.factories import PurchaseLineFactory, SupplierFactory, ToolTemplateFactory

pytestmark = pytest.mark.django_db


def test_количество_строки_должно_быть_больше_нуля() -> None:
    with pytest.raises(IntegrityError, match="supply_line_quantity_positive"):
        PurchaseLineFactory.create(quantity=Decimal("0"))


@pytest.mark.parametrize(
    ("kind", "category"),
    [(LineKind.MATERIAL, LineCategory.TOOL), (LineKind.TOOL, LineCategory.MATERIAL)],
)
def test_вид_строки_соответствует_категории(kind: LineKind, category: LineCategory) -> None:
    with pytest.raises(IntegrityError, match="supply_line_kind_matches_category"):
        PurchaseLineFactory.create(kind=kind, category=category)


def test_операция_указывается_только_у_строки_заказа() -> None:
    with pytest.raises(IntegrityError, match="supply_line_operation_needs_order"):
        PurchaseLineFactory.create(operation_id=uuid.uuid4(), order_id=None)


def test_переданная_в_закупку_строка_без_номера_заявки_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="supply_line_requisition_after_draft"):
        PurchaseLineFactory.create(status=LineStatus.SENT, sent_at=timezone.now())


def test_заказанная_строка_без_поставщика_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="supply_line_ordered_has_supplier"):
        PurchaseLineFactory.create(
            status=LineStatus.ORDERED,
            requisition_no="ЗЗ-1",
            sent_at=timezone.now(),
            po_number="ЗП-1",
            eta=date(2026, 11, 10),
        )


def test_заказанная_строка_с_поставщиком_номером_и_сроком_допустима() -> None:
    line = PurchaseLineFactory.create(
        status=LineStatus.ORDERED,
        requisition_no="ЗЗ-1",
        sent_at=timezone.now(),
        supplier=SupplierFactory.create(),
        po_number="ЗП-1",
        eta=date(2026, 11, 10),
    )
    assert line.status == LineStatus.ORDERED


def test_принятая_строка_без_количества_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="supply_line_received_has_receipt"):
        PurchaseLineFactory.create(
            status=LineStatus.RECEIVED,
            requisition_no="ЗЗ-1",
            sent_at=timezone.now(),
            received_at=date(2026, 11, 3),
        )


def test_выданная_строка_без_получателя_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="supply_line_issued_has_recipient"):
        PurchaseLineFactory.create(
            status=LineStatus.ISSUED,
            requisition_no="ЗЗ-1",
            sent_at=timezone.now(),
            received_at=date(2026, 11, 3),
            issued_at=date(2026, 11, 4),
        )


def test_выданная_строка_с_датой_и_получателем_допустима() -> None:
    line = PurchaseLineFactory.create(
        status=LineStatus.ISSUED,
        requisition_no="ЗЗ-1",
        sent_at=timezone.now(),
        received_at=date(2026, 11, 3),
        issued_at=date(2026, 11, 4),
        issued_to=EmployeeFactory.create(),
    )
    assert line.status == LineStatus.ISSUED


def test_резерв_без_даты_нарушает_constraint() -> None:
    with pytest.raises(IntegrityError, match="supply_line_reserved_has_date"):
        PurchaseLineFactory.create(
            status=LineStatus.RESERVED, requisition_no="ЗЗ-1", sent_at=timezone.now()
        )


def test_поставщик_уникален() -> None:
    SupplierFactory.create(name="ООО «Альфа»")
    with pytest.raises(IntegrityError):
        SupplierFactory.create(name="ООО «Альфа»")


def test_типовая_оснастка_не_бывает_материалом() -> None:
    with pytest.raises(IntegrityError, match="supply_tool_template_not_material"):
        ToolTemplateFactory.create(category=LineCategory.MATERIAL)


def test_типовая_оснастка_уникальна_на_участке() -> None:
    template = ToolTemplateFactory.create(name="Сопло")
    with pytest.raises(IntegrityError):
        ToolTemplateFactory.create(name="Сопло", work_center_id=template.work_center_id)
