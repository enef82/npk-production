"""Публичный интерфейс модуля «Заявки и калькуляция» для других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2, «Фасад»)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.sales import selectors
from src.sales.models import InquiryStage
from src.sales.services import demo as demo_services

__all__ = [
    "CalcMaterialBrief",
    "InquiryBrief",
    "InquiryStage",
    "OpenInquiry",
    "PlanOperationBrief",
    "get_calc_materials",
    "get_inquiries_brief",
    "get_stage_probabilities",
    "list_open_inquiries",
    "seed_demo",
]


@dataclass(frozen=True)
class InquiryBrief:
    id: UUID
    number: str
    customer_id: UUID
    customer_name: str
    product_name: str
    quantity: Decimal
    stage: str
    due_date: date
    manager_id: UUID
    # Итог калькуляции с НДС и вероятность этапа, % (`SalesSettings`).
    total: Decimal
    probability: Decimal
    order_id: UUID | None
    planned_start: date | None
    planned_finish: date | None


@dataclass(frozen=True)
class PlanOperationBrief:
    work_center_id: UUID
    hours: Decimal
    is_supply: bool
    planned_start: date | None
    planned_finish: date | None


@dataclass(frozen=True)
class CalcMaterialBrief:
    name: str
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True)
class OpenInquiry:
    inquiry: InquiryBrief
    operations: list[PlanOperationBrief]


def _brief(card: selectors.InquiryCard) -> InquiryBrief:
    return InquiryBrief(
        id=card.id,
        number=card.number,
        customer_id=card.customer_id,
        customer_name=card.customer_name,
        product_name=card.product_name,
        quantity=card.quantity,
        stage=card.stage,
        due_date=card.due_date,
        manager_id=card.manager_id,
        total=card.total,
        probability=card.probability,
        order_id=card.order_id,
        planned_start=card.planned_start,
        planned_finish=card.planned_finish,
    )


def get_inquiries_brief(ids: Iterable[UUID]) -> dict[UUID, InquiryBrief]:
    return {
        item.card.id: _brief(item.card)
        for item in selectors.list_inquiries_with_plan(ids=list(ids))
    }


def list_open_inquiries() -> list[OpenInquiry]:
    """Открытые заявки (новые, просчёт, согласование) — для портфеля и загрузки: итог,
    этап, вероятность, операции предварительного плана с датами, часами и участками."""

    return [
        OpenInquiry(
            inquiry=_brief(item.card),
            operations=[
                PlanOperationBrief(
                    work_center_id=op.work_center_id,
                    hours=op.hours,
                    is_supply=op.is_supply,
                    planned_start=op.planned_start,
                    planned_finish=op.planned_finish,
                )
                for op in item.operations
            ],
        )
        for item in selectors.list_inquiries_with_plan(open_only=True)
    ]


def get_stage_probabilities() -> dict[str, Decimal]:
    """Вероятность этапа заявки, % (`SalesSettings`: новые, просчёт, согласование КП) —
    подписи портфеля."""

    return selectors.stage_probabilities()


def get_calc_materials(inquiry_id: UUID) -> list[CalcMaterialBrief]:
    """Материалы калькуляции заявки в порядке калькуляции — потребность `supply` при
    запуске заказа. Нет заявки — пустой список."""

    detail = selectors.get_inquiry_detail(inquiry_id)
    if detail is None:
        return []
    return [
        CalcMaterialBrief(name=m.name, quantity=m.quantity, price=m.price) for m in detail.materials
    ]


def seed_demo() -> None:
    """Демо-заявки прототипа; запускать после `production.facade.seed_demo()`."""

    demo_services.seed_demo()
