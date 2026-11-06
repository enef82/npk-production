"""Публичный интерфейс модуля «Снабжение и склад» для других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4, «Фасад»).

Наружу — только датаклассы этого файла и UUID (И1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from src.supply import selectors

__all__ = [
    "LineBrief",
    "OrderSupplyStatus",
    "get_order_supply_status",
    "list_lines_by_operation",
    "seed_demo",
]


@dataclass(frozen=True)
class LineBrief:
    id: UUID
    order_id: UUID | None
    operation_id: UUID | None
    kind: str
    category: str
    name: str
    quantity: Decimal
    unit: str
    status: str
    need_date: date
    eta: date | None
    # Опоздание к потребности, календарные дни (`prLate`).
    late_days: int


@dataclass(frozen=True)
class OrderSupplyStatus:
    draft: int
    sent: int
    ordered: int
    received: int
    reserved: int
    issued: int
    late: int
    active_amount: Decimal


def list_lines_by_operation(ids: Iterable[UUID]) -> dict[UUID, list[LineBrief]]:
    """Строки потребности по операциям — «Закупка по операции» в карточке операции."""

    today = timezone.localdate()
    return {
        operation_id: [
            LineBrief(
                id=line.id,
                order_id=line.order_id,
                operation_id=line.operation_id,
                kind=line.kind,
                category=line.category,
                name=line.name,
                quantity=line.quantity,
                unit=line.unit,
                status=line.status,
                need_date=line.need_date,
                eta=line.eta,
                late_days=selectors.line_late(line, today),
            )
            for line in lines
        ]
        for operation_id, lines in selectors.lines_by_operation(ids).items()
    }


def get_order_supply_status(order_id: UUID) -> OrderSupplyStatus:
    """Строки заказа по статусам, число опаздывающих, сумма не выданного в цех."""

    c = selectors.order_status(order_id, timezone.localdate())
    return OrderSupplyStatus(
        draft=c.draft,
        sent=c.sent,
        ordered=c.ordered,
        received=c.received,
        reserved=c.reserved,
        issued=c.issued,
        late=c.late,
        active_amount=c.active_amount,
    )


def seed_demo() -> None:
    """Поставщики, типовая оснастка участков и потребность демо-заказов в разных
    статусах (`seedProc` прототипа). Запускать после `production`, `sales`."""

    # Импорт при вызове — тот же приём, что в `quality.facade`: демо читает заказы через
    # `production.facade`, и цикл импорта на загрузке не нужен.
    from src.supply.services import demo as demo_services

    demo_services.seed_demo()
