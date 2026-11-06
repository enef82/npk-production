"""Публичный интерфейс модуля «Оборудование и ТО» для других модулей (§3.6).

Наружу — только dataclass-проекции, модели не отдаются (И1): `energy` считает
удельный расход по `get_runtime`, сид приложения вызывает `seed_demo`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from src.equipment import selectors
from src.equipment.models import EquipmentStatus
from src.equipment.services.demo import seed_demo

__all__ = [
    "EquipmentBrief",
    "RuntimeRow",
    "get_runtime",
    "list_equipment",
    "seed_demo",
]


@dataclass(frozen=True)
class EquipmentBrief:
    id: UUID
    inventory_no: str
    name: str
    work_center_id: UUID | None
    status: EquipmentStatus
    operating_hours: Decimal


@dataclass(frozen=True)
class RuntimeRow:
    equipment_id: UUID
    date: date
    run: Decimal
    setup: Decimal
    idle: Decimal
    down: Decimal

    @property
    def machine_hours(self) -> Decimal:
        """Машино-часы для удельного расхода — работа и наладка под нагрузкой."""

        return self.run + self.setup


def list_equipment() -> list[EquipmentBrief]:
    return [
        EquipmentBrief(
            id=item.id,
            inventory_no=item.inventory_no,
            name=item.name,
            work_center_id=item.work_center_id,
            status=EquipmentStatus(item.status),
            operating_hours=selectors.operating_hours(item),
        )
        for item in selectors.list_equipment()
    ]


def get_runtime(date_from: date, date_to: date) -> list[RuntimeRow]:
    """Суточная наработка всех станков за период включительно."""

    return [
        RuntimeRow(
            equipment_id=log.equipment_id,
            date=log.date,
            run=log.run,
            setup=log.setup,
            idle=log.idle,
            down=log.down,
        )
        for log in selectors.runtime_between(date_from, date_to)
    ]
