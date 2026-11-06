"""Обработчики событий других модулей в «Снабжение и склад»."""

from __future__ import annotations

from src.core.events.models import OutboxEvent
from src.core.events.registry import subscribe
from src.supply.services.lines import generate_for_launched_order


@subscribe("production.order_launched")
def create_order_demand(event: OutboxEvent) -> None:
    """`production.order_launched` v1 (`aggregate_id` — заказ) → черновики строк
    материалов из калькуляции заявки и оснастки по участкам маршрута
    (`docs/events.md`). Идемпотентно по заказу."""

    generate_for_launched_order(event.aggregate_id)
