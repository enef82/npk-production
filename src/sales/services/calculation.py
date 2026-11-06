"""Калькуляция заявки: материалы, операции, связи, заполнение из шаблона,
предварительный план (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2).

Калькуляция правится, пока заявка открыта (новая, просчёт, согласование). Любая правка
под блокировкой заявки. Если план уже сформирован (у всех операций есть дата), правка
операций или связей пересчитывает его — как `schedule()` прототипа при `hasPlan`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.common.scheduling import ScheduleEdge, find_cycle, forward_pass, next_working_day
from src.production import facade as production
from src.sales.exceptions import (
    DependencyCycle,
    DependencyInvalid,
    InquiryClosed,
    InvalidValues,
    TemplateNotFound,
    WorkCenterNotFound,
)
from src.sales.models import (
    OPEN_STAGES,
    CalcMaterial,
    CalcOperation,
    CalcOperationDependency,
    Inquiry,
)
from src.sales.planning import centers_by_id, network

_HOURS = Decimal("0.01")
_QTY = Decimal("0.001")


@dataclass(frozen=True)
class MaterialDTO:
    name: str
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True)
class CalcOperationDTO:
    name: str
    work_center_id: UUID
    hours: Decimal
    people: int = 1
    not_before: date | None = None


def lock_inquiry(inquiry_id: UUID) -> Inquiry:
    inquiry = Inquiry.objects.select_for_update().get(id=inquiry_id)
    if inquiry.stage not in OPEN_STAGES:
        raise InquiryClosed
    return inquiry


def has_plan(inquiry: Inquiry) -> bool:
    operations = CalcOperation.objects.filter(inquiry=inquiry)
    return operations.exists() and not operations.filter(planned_start__isnull=True).exists()


def schedule_inquiry(inquiry: Inquiry) -> None:
    """Прямой проход от предварительного старта; «не раньше сегодня» к заявке не
    применяется (в прототипе — только к заказу)."""

    if inquiry.planned_start is None:
        return
    operations = list(CalcOperation.objects.filter(inquiry=inquiry).order_by("seq"))
    if not operations:
        return
    dependencies = list(CalcOperationDependency.objects.filter(successor__inquiry=inquiry))
    nodes, edges = network(operations, dependencies, centers_by_id())
    starts = forward_pass(nodes, edges, base=inquiry.planned_start)
    for op in operations:
        op.planned_start = starts[op.id]
    CalcOperation.objects.bulk_update(operations, ["planned_start"])


def _replan_if_planned(inquiry: Inquiry) -> None:
    if inquiry.planned_start is not None and has_plan(inquiry):
        schedule_inquiry(inquiry)


def _validate_material(data: MaterialDTO) -> None:
    if not data.name.strip() or data.quantity < 0 or data.price < 0:
        raise InvalidValues("Материал: наименование обязательно, количество и цена ≥ 0.")


def _validate_operation(data: CalcOperationDTO) -> None:
    if not data.name.strip() or data.hours < 0 or data.people < 1:
        raise InvalidValues(
            "Операция: наименование обязательно, трудоёмкость ≥ 0, исполнителей ≥ 1."
        )
    center = production.get_work_center(data.work_center_id)
    if center is None:
        raise WorkCenterNotFound
    if not center.is_supply and data.people > center.capacity:
        raise InvalidValues(f"Исполнителей больше мощности участка ({center.capacity}).")


def add_material(inquiry_id: UUID, data: MaterialDTO, *, actor_id: UUID) -> UUID:
    _validate_material(data)
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        top = CalcMaterial.objects.filter(inquiry=inquiry).aggregate(m=Max("sort_order"))["m"]
        material = CalcMaterial.objects.create(
            inquiry=inquiry,
            name=data.name.strip(),
            quantity=data.quantity,
            price=data.price,
            sort_order=(top or 0) + 1,
        )
    return material.id


def update_material(material_id: UUID, data: MaterialDTO, *, actor_id: UUID) -> None:
    _validate_material(data)
    with transaction.atomic(), actor_context(actor_id):
        inquiry_id = CalcMaterial.objects.values_list("inquiry_id", flat=True).get(id=material_id)
        lock_inquiry(inquiry_id)
        CalcMaterial.objects.filter(id=material_id).update(
            name=data.name.strip(),
            quantity=data.quantity,
            price=data.price,
            updated_at=timezone.now(),
        )


def delete_material(material_id: UUID, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        inquiry_id = CalcMaterial.objects.values_list("inquiry_id", flat=True).get(id=material_id)
        lock_inquiry(inquiry_id)
        CalcMaterial.objects.filter(id=material_id).delete()


def add_operation(inquiry_id: UUID, data: CalcOperationDTO, *, actor_id: UUID) -> UUID:
    """Новая операция в конец маршрута (номер = последний + 10). Без даты: план
    формируется отдельным действием; если план был — пересчитывается."""

    _validate_operation(data)
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        top = CalcOperation.objects.filter(inquiry=inquiry).aggregate(m=Max("seq"))["m"]
        had_plan = has_plan(inquiry)
        operation = CalcOperation.objects.create(
            inquiry=inquiry,
            seq=(top or 0) + 10,
            name=data.name.strip(),
            work_center_id=data.work_center_id,
            hours=data.hours,
            people=data.people,
            not_before=next_working_day(data.not_before) if data.not_before else None,
        )
        if had_plan:
            schedule_inquiry(inquiry)
    return operation.id


def update_operation(operation_id: UUID, data: CalcOperationDTO, *, actor_id: UUID) -> None:
    _validate_operation(data)
    with transaction.atomic(), actor_context(actor_id):
        inquiry_id = CalcOperation.objects.values_list("inquiry_id", flat=True).get(id=operation_id)
        inquiry = lock_inquiry(inquiry_id)
        operation = CalcOperation.objects.get(id=operation_id)
        operation.name = data.name.strip()
        operation.work_center_id = data.work_center_id
        operation.hours = data.hours
        operation.people = data.people
        operation.not_before = next_working_day(data.not_before) if data.not_before else None
        operation.save(
            update_fields=["name", "work_center_id", "hours", "people", "not_before", "updated_at"]
        )
        _replan_if_planned(inquiry)


def delete_operation(operation_id: UUID, *, actor_id: UUID) -> None:
    with transaction.atomic(), actor_context(actor_id):
        inquiry_id = CalcOperation.objects.values_list("inquiry_id", flat=True).get(id=operation_id)
        inquiry = lock_inquiry(inquiry_id)
        CalcOperation.objects.filter(id=operation_id).delete()
        _replan_if_planned(inquiry)


def set_predecessors(
    operation_id: UUID, predecessor_ids: Sequence[UUID], *, actor_id: UUID
) -> None:
    """Предшественники операции целиком (колонка «Предш.» плана). Цикл — обходом графа
    калькуляции под блокировкой заявки; «одна заявка» дублирует триггер БД."""

    wanted = list(dict.fromkeys(predecessor_ids))
    with transaction.atomic(), actor_context(actor_id):
        inquiry_id = CalcOperation.objects.values_list("inquiry_id", flat=True).get(id=operation_id)
        inquiry = lock_inquiry(inquiry_id)
        if operation_id in wanted:
            raise DependencyInvalid("Операция не может зависеть от самой себя.")
        siblings = set(CalcOperation.objects.filter(inquiry=inquiry).values_list("id", flat=True))
        if any(pred_id not in siblings for pred_id in wanted):
            raise DependencyInvalid
        others = [
            ScheduleEdge(dep.predecessor_id, dep.successor_id)
            for dep in CalcOperationDependency.objects.filter(successor__inquiry=inquiry).exclude(
                successor_id=operation_id
            )
        ]
        new = [ScheduleEdge(pred_id, operation_id) for pred_id in wanted]
        if find_cycle(siblings, others + new) is not None:
            raise DependencyCycle
        CalcOperationDependency.objects.filter(successor_id=operation_id).delete()
        CalcOperationDependency.objects.bulk_create(
            [
                CalcOperationDependency(predecessor_id=pred_id, successor_id=operation_id)
                for pred_id in wanted
            ]
        )
        _replan_if_planned(inquiry)


def link_sequential(inquiry_id: UUID, *, actor_id: UUID) -> None:
    """«Связать всё последовательно»: каждая операция — после предыдущей по номеру."""

    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        operations = list(CalcOperation.objects.filter(inquiry=inquiry).order_by("seq"))
        CalcOperationDependency.objects.filter(successor__inquiry=inquiry).delete()
        CalcOperationDependency.objects.bulk_create(
            [
                CalcOperationDependency(predecessor=prev, successor=nxt)
                for prev, nxt in zip(operations, operations[1:], strict=False)
            ]
        )
        _replan_if_planned(inquiry)


def fill_from_template(inquiry_id: UUID, template_id: UUID | None, *, actor_id: UUID) -> None:
    """«Заполнить из шаблона» (`fillFromTpl`): материалы — количество × количество
    изделий; операции со связями, трудоёмкость × количество, если операция зависит от
    количества. Прежняя калькуляция и план заменяются."""

    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        template = production.get_template(template_id or inquiry.template_id or "")
        if template is None:
            raise TemplateNotFound
        replace_calculation(inquiry, template)


def replace_calculation(inquiry: Inquiry, template: production.TemplateBrief) -> None:
    """Калькуляция и маршрут из шаблона вместо прежних; план сбрасывается. Вызывается
    внутри транзакции вызывающего."""

    qty = inquiry.quantity
    CalcMaterial.objects.filter(inquiry=inquiry).delete()
    CalcOperation.objects.filter(inquiry=inquiry).delete()
    CalcMaterial.objects.bulk_create(
        [
            CalcMaterial(
                inquiry=inquiry,
                name=m.name,
                quantity=(m.qty_per_unit * qty).quantize(_QTY),
                price=m.price,
                sort_order=i,
            )
            for i, m in enumerate(template.materials)
        ]
    )
    operations = CalcOperation.objects.bulk_create(
        [
            CalcOperation(
                inquiry=inquiry,
                seq=(i + 1) * 10,
                name=op.name,
                work_center_id=op.work_center_id,
                hours=(op.hours * qty).quantize(_HOURS) if op.scales_with_qty else op.hours,
                people=op.people,
            )
            for i, op in enumerate(template.operations)
        ]
    )
    CalcOperationDependency.objects.bulk_create(
        [
            CalcOperationDependency(predecessor=operations[pred], successor=operations[i])
            for i, op in enumerate(template.operations)
            for pred in op.predecessor_indexes
        ]
    )
    inquiry.template_id = template.id
    if not inquiry.product_name:
        inquiry.product_name = template.name
    inquiry.planned_start = None
    inquiry.save(update_fields=["template_id", "product_name", "planned_start", "updated_at"])


def build_plan(inquiry_id: UUID, planned_start: date | None, *, actor_id: UUID) -> None:
    """«Сформировать / пересчитать план» от даты начала работ (по умолчанию — через
    неделю, как в прототипе)."""

    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        start = planned_start or inquiry.planned_start or timezone.localdate() + timedelta(days=7)
        inquiry.planned_start = next_working_day(start)
        inquiry.save(update_fields=["planned_start", "updated_at"])
        if not CalcOperation.objects.filter(inquiry=inquiry).exists():
            raise InvalidValues("В калькуляции нет операций — планировать нечего.")
        schedule_inquiry(inquiry)
