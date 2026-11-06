"""Запись результата контроля операции (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3;
прототип `opDialog`, блок «Контроль качества»).

Запись и строка журнала заказа (`production.facade.add_journal_entry(kind="qc")`) — в
одной транзакции БД (И4): журнал пишется синхронным вызовом фасада внутри неё. Права —
в API; сервис проверяет правила: точка контроля у участка, заказ запущен, количества,
вид дефекта той же точки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.production import facade as production
from src.quality.exceptions import (
    DefectNotClassified,
    FutureDate,
    InvalidCounts,
    NoInspectionPoint,
    OperationNotFound,
    OrderNotLaunched,
    ReferenceNotFound,
)
from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord

# Этапы заказа, на которых пишется контроль (`started` прототипа). Входной контроль
# снабжения — с момента создания заказа (этап «Запуск»), пока заказ не отгружен.
RECORDING_STAGES = (
    production.OrderStage.PREP,
    production.OrderStage.PROD,
    production.OrderStage.QC,
)
SUPPLY_RECORDING_STAGES = (production.OrderStage.LAUNCH, *RECORDING_STAGES)


@dataclass(frozen=True)
class InspectionDTO:
    checked: int
    rework: int = 0
    scrap: int = 0
    defect_type_id: UUID | None = None
    cause_id: UUID | None = None
    comment: str = ""
    date: date | None = None


@dataclass(frozen=True)
class RecordResult:
    record_id: UUID
    # Списание — нужно повторное изготовление (предупреждение API, §3.3).
    needs_remake: bool


def _validate(
    point: InspectionPoint, data: InspectionDTO
) -> tuple[DefectType | None, DefectCause | None]:
    if data.checked <= 0 or data.rework < 0 or data.scrap < 0:
        raise InvalidCounts
    if data.rework + data.scrap > data.checked:
        raise InvalidCounts("Брака больше, чем проверено.")
    if data.rework + data.scrap == 0:
        return None, None
    if data.defect_type_id is None or data.cause_id is None:
        raise DefectNotClassified
    defect_type = DefectType.objects.filter(
        id=data.defect_type_id, inspection_point=point, is_active=True
    ).first()
    if defect_type is None:
        raise ReferenceNotFound("Вид дефекта не относится к точке контроля участка.")
    cause = DefectCause.objects.filter(id=data.cause_id, is_active=True).first()
    if cause is None:
        raise ReferenceNotFound("Причина брака не найдена.")
    return defect_type, cause


def journal_text(
    point_name: str,
    checked: int,
    rework: int,
    scrap: int,
    defect_type: str,
    cause: str,
    comment: str,
) -> str:
    text = f"{point_name}: проверено {checked}"
    if rework + scrap:
        text += (
            f", брак {rework + scrap} (доработка {rework}, списание {scrap}) — "
            f"{defect_type}, причина: {cause}"
        )
    else:
        text += ", замечаний нет"
    return text + (f". {comment}" if comment else "")


def record_inspection(
    operation_id: UUID,
    data: InspectionDTO,
    *,
    actor_id: UUID,
    inspector_id: UUID,
) -> RecordResult:
    operation = production.get_operations_brief([operation_id]).get(operation_id)
    if operation is None:
        raise OperationNotFound
    order = production.get_orders_brief([operation.order_id])[operation.order_id]
    stages = SUPPLY_RECORDING_STAGES if operation.is_supply else RECORDING_STAGES
    if order.stage not in stages:
        raise OrderNotLaunched
    day = data.date or timezone.localdate()
    if day > timezone.localdate():
        raise FutureDate
    comment = data.comment.strip()
    with transaction.atomic(), actor_context(actor_id):
        point = InspectionPoint.objects.filter(
            work_center_id=operation.work_center_id, is_active=True
        ).first()
        if point is None:
            raise NoInspectionPoint
        defect_type, cause = _validate(point, data)
        record = InspectionRecord.objects.create(
            operation_id=operation.id,
            order_id=operation.order_id,
            work_center_id=operation.work_center_id,
            date=day,
            inspector_id=inspector_id,
            checked=data.checked,
            rework=data.rework,
            scrap=data.scrap,
            defect_type=defect_type,
            cause=cause,
            comment=comment,
        )
        production.add_journal_entry(
            operation.order_id,
            production.JournalKind.QC,
            journal_text(
                point.name,
                data.checked,
                data.rework,
                data.scrap,
                defect_type.name if defect_type else "",
                cause.name if cause else "",
                comment,
            ),
            operation_id=operation.id,
            author_employee_id=inspector_id,
        )
    return RecordResult(record_id=record.id, needs_remake=data.scrap > 0)
