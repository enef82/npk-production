"""События, которые публикует модуль «Оборудование и ТО». Каталог — `docs/events.md`."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from src.core.events.base import DomainEvent


@dataclasses.dataclass(frozen=True)
class RepairWorkerHours:
    employee_id: UUID
    hours: Decimal


@dataclasses.dataclass(frozen=True)
class RepairClosed(DomainEvent):
    """Ремонт, авария или ТО закрыты (`done`). Подписчик — `timesheet`: часы
    исполнителей ложатся в разноску «ремонт и ТО» на дату ремонта."""

    event_type: ClassVar[str] = "equipment.repair_closed"

    equipment_id: UUID
    date: date
    number: str
    workers: tuple[RepairWorkerHours, ...]
