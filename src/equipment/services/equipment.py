"""Карточка оборудования, состояние, виды ТО (§3.6). Единственное место транзакций
для `Equipment` и `MaintenanceType` (И3).

Права проверяются в API и админке, не здесь (как в `production` ИС): сервис вызывают
и сид демо-данных, у которого пользователя нет.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.equipment import selectors
from src.equipment.exceptions import InvalidHours, InventoryNoTaken, MaintenanceCodeTaken
from src.equipment.models import Equipment, EquipmentStatus, MaintenanceType


def as_actor(actor_id: UUID | None) -> AbstractContextManager[object]:
    """Контекст истории pghistory: с актором — для пользовательских действий, без —
    для сида демо-данных."""

    return actor_context(actor_id) if actor_id is not None else nullcontext()


@dataclass(frozen=True)
class EquipmentDTO:
    inventory_no: str
    name: str
    work_center_id: UUID | None = None
    control_system: str = ""
    connection: str = ""
    operating_hours_initial: Decimal = Decimal("0")


def _apply(equipment: Equipment, data: EquipmentDTO) -> None:
    if data.operating_hours_initial < 0:
        raise InvalidHours("Начальные моточасы не могут быть отрицательными.")
    equipment.inventory_no = data.inventory_no.strip()
    equipment.name = data.name.strip()
    equipment.work_center_id = data.work_center_id
    equipment.control_system = data.control_system.strip()
    equipment.connection = data.connection.strip()
    equipment.operating_hours_initial = data.operating_hours_initial


def create_equipment(data: EquipmentDTO, *, actor_id: UUID | None) -> Equipment:
    with transaction.atomic(), as_actor(actor_id):
        if Equipment.objects.filter(inventory_no=data.inventory_no.strip()).exists():
            raise InventoryNoTaken
        equipment = Equipment()
        _apply(equipment, data)
        equipment.save()
    return equipment


def update_equipment(equipment_id: UUID, data: EquipmentDTO, *, actor_id: UUID | None) -> None:
    with transaction.atomic(), as_actor(actor_id):
        equipment = Equipment.objects.select_for_update().get(id=equipment_id)
        if (
            Equipment.objects.filter(inventory_no=data.inventory_no.strip())
            .exclude(id=equipment_id)
            .exists()
        ):
            raise InventoryNoTaken
        _apply(equipment, data)
        equipment.save()


def set_equipment_status(
    equipment_id: UUID, status: EquipmentStatus, *, actor_id: UUID | None
) -> None:
    """Ручная смена состояния (селект «Состояние» прототипа). Открытый или закрытый
    ремонт пересчитывает состояние заново (`refresh_status`)."""

    with transaction.atomic(), as_actor(actor_id):
        equipment = Equipment.objects.select_for_update().get(id=equipment_id)
        equipment.status = status
        equipment.save(update_fields=["status", "updated_at"])


def refresh_status(equipment_id: UUID) -> None:
    """Состояние по журналу ремонтов: незакрытая авария/ремонт → «в ремонте»,
    незакрытое ТО → «на ТО», иначе «работает» (правило `repDialog` прототипа).
    Вызывается внутри транзакции сервиса ремонта."""

    if selectors.has_open_repairs(equipment_id, maintenance=False):
        status = EquipmentStatus.REPAIR
    elif selectors.has_open_repairs(equipment_id, maintenance=True):
        status = EquipmentStatus.MAINTENANCE
    else:
        status = EquipmentStatus.RUN
    Equipment.objects.filter(id=equipment_id).exclude(status=status).update(status=status)


@dataclass(frozen=True)
class MaintenanceTypeDTO:
    code: str
    interval_hours: Decimal
    scope: str = ""


def _apply_type(mtype: MaintenanceType, data: MaintenanceTypeDTO) -> None:
    if data.interval_hours <= 0:
        raise InvalidHours("Интервал ТО должен быть больше нуля.")
    mtype.code = data.code.strip()
    mtype.interval_hours = data.interval_hours
    mtype.scope = data.scope.strip()


def create_maintenance_type(
    equipment_id: UUID, data: MaintenanceTypeDTO, *, actor_id: UUID | None
) -> MaintenanceType:
    with transaction.atomic(), as_actor(actor_id):
        equipment = Equipment.objects.select_for_update().get(id=equipment_id)
        if MaintenanceType.objects.filter(equipment=equipment, code=data.code.strip()).exists():
            raise MaintenanceCodeTaken
        mtype = MaintenanceType(equipment=equipment)
        _apply_type(mtype, data)
        mtype.save()
    return mtype


def update_maintenance_type(
    maintenance_type_id: UUID, data: MaintenanceTypeDTO, *, actor_id: UUID | None
) -> None:
    with transaction.atomic(), as_actor(actor_id):
        mtype = MaintenanceType.objects.select_for_update().get(id=maintenance_type_id)
        if (
            MaintenanceType.objects.filter(equipment_id=mtype.equipment_id, code=data.code.strip())
            .exclude(id=maintenance_type_id)
            .exists()
        ):
            raise MaintenanceCodeTaken
        _apply_type(mtype, data)
        mtype.save()
