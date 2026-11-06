"""Обработчики событий других модулей в «Табель»."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from src.core.events.models import OutboxEvent
from src.core.events.registry import subscribe
from src.timesheet.services.repair import RepairWorkerHours, apply_repair_hours


@subscribe("equipment.repair_closed")
def apply_repair_hours_to_timesheet(event: OutboxEvent) -> None:
    """`equipment.repair_closed` v1: `equipment_id`, `date` (ISO), `number`,
    `workers: [{employee_id, hours (строка)}]` → разноска «ремонт и ТО»
    (`docs/events.md`). Часы — строкой, разбираются в `Decimal` без `float` (И6)."""

    payload = event.payload
    apply_repair_hours(
        number=str(payload["number"]),
        day=date.fromisoformat(payload["date"]),
        workers=[
            RepairWorkerHours(employee_id=UUID(w["employee_id"]), hours=Decimal(str(w["hours"])))
            for w in payload.get("workers", [])
        ],
    )
