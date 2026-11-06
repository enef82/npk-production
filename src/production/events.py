"""События, которые публикует модуль «Производство». Каталог — `docs/events.md`."""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import ClassVar
from uuid import UUID

from src.core.events.base import DomainEvent


@dataclasses.dataclass(frozen=True)
class OrderLaunched(DomainEvent):
    """Создан производственный заказ (запуск заявки). Подписчик — `supply`
    (потребность в материалах и оснастке)."""

    event_type: ClassVar[str] = "production.order_launched"

    inquiry_id: UUID | None
    planned_start: date


@dataclasses.dataclass(frozen=True)
class OrderStageChanged(DomainEvent):
    event_type: ClassVar[str] = "production.order_stage_changed"

    from_stage: str
    to_stage: str


@dataclasses.dataclass(frozen=True)
class OperationApproved(DomainEvent):
    """Виза операции; `aggregate_id` — операция."""

    event_type: ClassVar[str] = "production.operation_approved"

    order_id: UUID
    work_center_id: UUID
