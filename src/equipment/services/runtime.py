"""Наработка за сутки (§3.6, `machDialog` прототипа: «Записать смену»). Единственное
место транзакций для `RuntimeLog` (И3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.equipment.exceptions import (
    DayOverflow,
    FutureDate,
    InvalidHours,
    ReasonRequired,
    ReferenceNotFound,
)
from src.equipment.models import (
    DownReason,
    Equipment,
    IdleReason,
    RuntimeLog,
    RuntimeSource,
)
from src.equipment.services.equipment import as_actor

DAY_LIMIT = Decimal("24")
ZERO = Decimal("0")


@dataclass(frozen=True)
class RuntimeDTO:
    date: date
    run: Decimal = ZERO
    setup: Decimal = ZERO
    idle: Decimal = ZERO
    down: Decimal = ZERO
    idle_reason_id: UUID | None = None
    down_reason_id: UUID | None = None
    source: RuntimeSource = RuntimeSource.MANUAL


def _check(data: RuntimeDTO) -> None:
    if data.date > timezone.localdate():
        raise FutureDate
    if min(data.run, data.setup, data.idle, data.down) < 0:
        raise InvalidHours
    if data.run + data.setup + data.idle + data.down > DAY_LIMIT:
        raise DayOverflow
    if data.idle > 0 and data.idle_reason_id is None:
        raise ReasonRequired("Укажите причину простоя.")
    if data.down > 0 and data.down_reason_id is None:
        raise ReasonRequired("Укажите причину остановки.")


def record_runtime(equipment_id: UUID, data: RuntimeDTO, *, actor_id: UUID | None) -> RuntimeLog:
    """Смена за сутки — заменяет прежнюю запись тех же суток (как в прототипе).
    Причина без часов не сохраняется: она бы попала в Парето с нулём."""

    _check(data)
    idle_reason = (
        IdleReason.objects.filter(id=data.idle_reason_id, is_active=True).first()
        if data.idle > 0 and data.idle_reason_id is not None
        else None
    )
    down_reason = (
        DownReason.objects.filter(id=data.down_reason_id, is_active=True).first()
        if data.down > 0 and data.down_reason_id is not None
        else None
    )
    if (data.idle > 0 and idle_reason is None) or (data.down > 0 and down_reason is None):
        raise ReferenceNotFound
    with transaction.atomic(), as_actor(actor_id):
        equipment = Equipment.objects.select_for_update().get(id=equipment_id)
        log, _ = RuntimeLog.objects.update_or_create(
            equipment=equipment,
            date=data.date,
            defaults={
                "run": data.run,
                "setup": data.setup,
                "idle": data.idle,
                "down": data.down,
                "idle_reason": idle_reason,
                "down_reason": down_reason,
                "source": data.source,
            },
        )
    return log
