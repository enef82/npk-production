"""Журнал аварий, ремонтов и ТО (§3.6, `repDialog` прототипа). Единственное место
транзакций для `Repair`, `RepairWorker` и `MaintenanceRecord` (И3).

Закрытие (`close_repair`) в одной транзакции: статус `done`, простой — в наработку
суток начала, для вида «ТО» — запись `MaintenanceRecord`, событие
`equipment.repair_closed` (И4), пересчёт состояния оборудования.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.events.publisher import publish
from src.core.numbering import facade as numbering
from src.core.org import facade as org
from src.equipment import selectors
from src.equipment.calculations import hours_between, is_working_day
from src.equipment.events import RepairClosed, RepairWorkerHours
from src.equipment.exceptions import (
    CloseRequirementsNotMet,
    DescriptionRequired,
    DuplicateWorker,
    EmployeeNotFound,
    FinishBeforeStart,
    InvalidHours,
    MaintenanceTypeMismatch,
    ReferenceNotFound,
    invalid_transition_as,
)
from src.equipment.exceptions import RepairClosed as RepairClosedError
from src.equipment.models import (
    DownReason,
    Equipment,
    FailureCategory,
    MaintenanceRecord,
    MaintenanceType,
    Repair,
    RepairKind,
    RepairStatus,
    RepairWorker,
    RuntimeLog,
    RuntimeSource,
)
from src.equipment.services.equipment import as_actor, refresh_status

NUMERATOR_CODE = "equipment.repair"
# Простой ремонта ложится в наработку суток не больше чем на смену (как в прототипе:
# `Math.min(8, repDown(r))`) — остальное время станок и так не работал бы.
MAX_DOWN_PER_SHIFT = Decimal("8")
ZERO = Decimal("0")


@dataclass(frozen=True)
class WorkerDTO:
    employee_id: UUID
    hours: Decimal


@dataclass(frozen=True)
class RepairDTO:
    kind: RepairKind
    started_at: datetime
    description: str
    finished_at: datetime | None = None
    maintenance_type_id: UUID | None = None
    category_id: UUID | None = None
    alarm_code: str = ""
    fix: str = ""
    parts: str = ""
    workers: list[WorkerDTO] = field(default_factory=list)


def _check_workers(workers: list[WorkerDTO]) -> None:
    ids = [worker.employee_id for worker in workers]
    if len(ids) != len(set(ids)):
        raise DuplicateWorker
    if any(worker.hours <= 0 for worker in workers):
        raise InvalidHours("Часы исполнителя должны быть больше нуля.")
    active = {brief.id for brief in org.list_active_employees()}
    if not set(ids) <= active:
        raise EmployeeNotFound


def _apply(repair: Repair, data: RepairDTO) -> None:
    if not data.description.strip():
        raise DescriptionRequired
    if data.finished_at is not None and data.finished_at < data.started_at:
        raise FinishBeforeStart
    mtype: MaintenanceType | None = None
    if data.kind == RepairKind.MAINTENANCE and data.maintenance_type_id is not None:
        mtype = MaintenanceType.objects.filter(
            id=data.maintenance_type_id, equipment_id=repair.equipment_id
        ).first()
    if data.kind == RepairKind.MAINTENANCE:
        if mtype is None:
            raise MaintenanceTypeMismatch
    elif data.maintenance_type_id is not None:
        raise MaintenanceTypeMismatch
    category: FailureCategory | None = None
    if data.category_id is not None:
        category = FailureCategory.objects.filter(id=data.category_id, is_active=True).first()
        if category is None:
            raise ReferenceNotFound("Категория отказа не найдена.")
    repair.kind = data.kind
    repair.maintenance_type = mtype
    repair.started_at = data.started_at
    repair.finished_at = data.finished_at
    repair.category = category
    repair.alarm_code = data.alarm_code.strip()
    repair.description = data.description.strip()
    repair.fix = data.fix.strip()
    repair.parts = data.parts.strip()


def _replace_workers(repair: Repair, workers: list[WorkerDTO]) -> None:
    RepairWorker.objects.filter(repair=repair).delete()
    RepairWorker.objects.bulk_create(
        [
            RepairWorker(repair=repair, employee_id=worker.employee_id, hours=worker.hours)
            for worker in workers
        ]
    )


def create_repair(equipment_id: UUID, data: RepairDTO, *, actor_id: UUID | None) -> Repair:
    """Регистрация аварии, ремонта или ТО — статус «зарегистрирована»; оборудование
    переходит в ремонт (или на ТО)."""

    _check_workers(data.workers)
    with transaction.atomic(), as_actor(actor_id):
        equipment = Equipment.objects.select_for_update().get(id=equipment_id)
        repair = Repair(equipment=equipment)
        _apply(repair, data)
        repair.number = numbering.issue_number(NUMERATOR_CODE)
        repair.save()
        _replace_workers(repair, data.workers)
        refresh_status(equipment.id)
    return repair


def _lock_open(repair_id: UUID) -> Repair:
    repair = Repair.objects.select_for_update().get(id=repair_id)
    if repair.status == RepairStatus.DONE:
        raise RepairClosedError
    return repair


def update_repair(repair_id: UUID, data: RepairDTO, *, actor_id: UUID | None) -> None:
    """Правка незакрытой записи. Закрытая не правится: её часы уже ушли событием
    в табель, и молчаливая правка разошлась бы с ним."""

    _check_workers(data.workers)
    with transaction.atomic(), as_actor(actor_id):
        repair = _lock_open(repair_id)
        _apply(repair, data)
        repair.save()
        _replace_workers(repair, data.workers)
        refresh_status(repair.equipment_id)


def start_repair(repair_id: UUID, *, actor_id: UUID | None) -> None:
    """`open → work` («В ремонт»)."""

    with transaction.atomic(), as_actor(actor_id):
        repair = Repair.objects.select_for_update().get(id=repair_id)
        with invalid_transition_as("В ремонт переводится только зарегистрированная запись."):
            repair.mark_in_work()
        repair.save(update_fields=["status", "updated_at"])


def _add_downtime_to_runtime(repair: Repair) -> None:
    """Простой — в наработку суток начала (`repDialog.commit` прототипа): отказ
    увеличивается, работа уменьшается на то же время; сумма суток не растёт."""

    downtime = min(MAX_DOWN_PER_SHIFT, hours_between(repair.started_at, _finished(repair)))
    if downtime <= 0:
        return
    reason = DownReason.objects.filter(repair_kind=repair.kind).first()
    if reason is None:
        raise ReferenceNotFound(
            f"Нет причины остановки для вида «{RepairKind(repair.kind).label}» — "
            "заполните справочник причин остановки."
        )
    day = timezone.localdate(repair.started_at)
    log = (
        RuntimeLog.objects.select_for_update().filter(equipment=repair.equipment, date=day).first()
    )
    if log is not None:
        log.down = min(MAX_DOWN_PER_SHIFT, log.down + downtime)
        log.run = max(ZERO, log.run - downtime)
        log.down_reason = reason
        log.save(update_fields=["down", "run", "down_reason", "updated_at"])
    elif is_working_day(day):
        RuntimeLog.objects.create(
            equipment=repair.equipment,
            date=day,
            down=downtime,
            down_reason=reason,
            source=RuntimeSource.MANUAL,
        )


def _finished(repair: Repair) -> datetime:
    assert repair.finished_at is not None
    return repair.finished_at


def close_repair(
    repair_id: UUID, *, finished_at: datetime | None = None, actor_id: UUID | None
) -> None:
    """«Устранено — закрыть»: проверки прототипа — окончание, исполнители с часами,
    категория для аварии."""

    with transaction.atomic(), as_actor(actor_id):
        repair = _lock_open(repair_id)
        if finished_at is not None:
            repair.finished_at = finished_at
        if repair.finished_at is None:
            raise CloseRequirementsNotMet("Укажите окончание простоя.")
        if repair.finished_at < repair.started_at:
            raise FinishBeforeStart
        workers = list(RepairWorker.objects.filter(repair=repair).order_by("-hours", "id"))
        if not workers:
            raise CloseRequirementsNotMet("Укажите исполнителей и их часы.")
        if repair.kind == RepairKind.FAILURE and repair.category_id is None:
            raise CloseRequirementsNotMet("Укажите категорию отказа — по ней строится статистика.")
        with invalid_transition_as("Запись уже закрыта."):
            repair.mark_done()
        repair.save(update_fields=["status", "finished_at", "updated_at"])

        _add_downtime_to_runtime(repair)
        repair_day = timezone.localdate(repair.started_at)
        if repair.kind == RepairKind.MAINTENANCE and repair.maintenance_type_id is not None:
            MaintenanceRecord.objects.create(
                maintenance_type_id=repair.maintenance_type_id,
                date=repair_day,
                at_hours=selectors.current_operating_hours(repair.equipment_id),
                performed_by_id=workers[0].employee_id,
            )
        publish(
            RepairClosed(
                aggregate_id=repair.id,
                equipment_id=repair.equipment_id,
                date=repair_day,
                number=repair.number,
                workers=tuple(
                    RepairWorkerHours(employee_id=worker.employee_id, hours=worker.hours)
                    for worker in workers
                ),
            )
        )
        refresh_status(repair.equipment_id)


@dataclass(frozen=True)
class MaintenanceDTO:
    started_at: datetime
    finished_at: datetime
    workers: list[WorkerDTO]
    comment: str = ""


def perform_maintenance(
    maintenance_type_id: UUID, data: MaintenanceDTO, *, actor_id: UUID | None
) -> Repair:
    """«Провести» ТО из карточки станка: запись вида «ТО» сразу закрывается — одна
    транзакция, без промежуточного состояния «на ТО»."""

    with transaction.atomic(), as_actor(actor_id):
        mtype = MaintenanceType.objects.select_related("equipment").get(id=maintenance_type_id)
        description = f"{mtype.code}: {mtype.scope}" if mtype.scope else mtype.code
        repair = create_repair(
            mtype.equipment_id,
            RepairDTO(
                kind=RepairKind.MAINTENANCE,
                maintenance_type_id=mtype.id,
                started_at=data.started_at,
                finished_at=data.finished_at,
                description=description,
                fix=data.comment.strip() or "выполнено по регламенту",
                workers=data.workers,
            ),
            actor_id=actor_id,
        )
        close_repair(repair.id, actor_id=actor_id)
    # Перечитываем, а не `refresh_from_db`: защищённое FSM-поле присваиванием не меняется.
    return Repair.objects.get(id=repair.id)
