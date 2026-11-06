"""Справочник кодов вида времени и профили работников — правка из админки через
сервис (CLAUDE.md §5), единственное место транзакций для этих моделей (И3)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.timesheet.exceptions import InvalidAllocation
from src.timesheet.models import TimeCode, WorkerProfile


@dataclass(frozen=True)
class TimeCodeDTO:
    code: str
    name: str
    is_work: bool
    is_allocatable: bool
    cost_multiplier: Decimal
    sort_order: int = 0


def save_time_code(time_code_id: UUID | None, data: TimeCodeDTO, *, actor_id: UUID) -> TimeCode:
    if data.is_allocatable and not data.is_work:
        raise InvalidAllocation("Разносить на объекты можно только рабочее время.")
    with transaction.atomic(), actor_context(actor_id):
        code = (
            TimeCode.objects.select_for_update().get(id=time_code_id)
            if time_code_id is not None
            else TimeCode()
        )
        code.code = data.code.strip()
        code.name = data.name.strip()
        code.is_work = data.is_work
        code.is_allocatable = data.is_allocatable
        code.cost_multiplier = data.cost_multiplier
        code.sort_order = data.sort_order
        code.save()
        return code


@dataclass(frozen=True)
class WorkerProfileDTO:
    work_center_id: UUID | None
    hourly_rate: Decimal


def save_worker_profile(
    employee_id: UUID, data: WorkerProfileDTO, *, actor_id: UUID
) -> WorkerProfile:
    with transaction.atomic(), actor_context(actor_id):
        profile, _ = WorkerProfile.objects.update_or_create(
            employee_id=employee_id,
            defaults={"work_center_id": data.work_center_id, "hourly_rate": data.hourly_rate},
        )
        return profile
