"""События, которые публикует модуль «Заявки и калькуляция». Каталог — `docs/events.md`."""

from __future__ import annotations

import dataclasses
from typing import ClassVar
from uuid import UUID

from src.core.events.base import DomainEvent


@dataclasses.dataclass(frozen=True)
class InquiryLaunched(DomainEvent):
    """Заявка запущена в производство; `aggregate_id` — заявка."""

    event_type: ClassVar[str] = "sales.inquiry_launched"

    order_id: UUID
