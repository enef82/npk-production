"""Производственный заказ: создание из заявки, этапы с визами, ответственные этапов,
сдвиг и пересчёт плана (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1).

Права проверяются в API и админке, не здесь (как в ИС): сервис вызывает и `sales` при
запуске, у которого своя проверка права. Сервис получает решение API в виде флага
`may_approve` — «пользователь вправе поставить визу текущего этапа», потому что правило
«нет визы, но переводит ответственный — виза ставится вместе с переходом» меняет данные.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.common.scheduling import ScheduleEdge, add_working_days, find_cycle
from src.core.events.publisher import publish
from src.core.numbering import facade as numbering
from src.core.org import facade as org
from src.production import selectors
from src.production.events import OrderLaunched, OrderStageChanged
from src.production.exceptions import (
    AlreadyApproved,
    InvalidLaunchData,
    OrderClosed,
    ReasonRequired,
    StageRequirementsNotMet,
    StageSkip,
    TemplateNotFound,
    VisaRequired,
    WorkCenterNotFound,
    invalid_transition_as,
)
from src.production.models import (
    ORDER_STAGE_SEQUENCE,
    JournalKind,
    Operation,
    OperationDependency,
    OperationStatus,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
    ProductionSettings,
    ProductTemplate,
    WorkCenter,
    WorkPhase,
)
from src.production.services.common import (
    ensure_active_employee,
    fmt_date,
    get_employee,
    journal,
    lock_order,
    reschedule,
)

NUMERATOR_CODE = "production.order"

_FORWARD = {
    OrderStage.LAUNCH: "to_prep",
    OrderStage.PREP: "to_prod",
    OrderStage.PROD: "to_qc",
    OrderStage.QC: "to_done",
}
_BACKWARD = {
    OrderStage.PREP: "back_to_launch",
    OrderStage.PROD: "back_to_prep",
    OrderStage.QC: "back_to_prod",
    OrderStage.DONE: "back_to_qc",
}


@dataclass(frozen=True)
class LaunchOperation:
    seq: int
    name: str
    work_center_id: UUID
    hours: Decimal
    people: int
    not_before: date | None = None
    # Индексы предшественников в списке `LaunchData.operations`.
    predecessor_indexes: tuple[int, ...] = ()


@dataclass(frozen=True)
class LaunchData:
    """Что `sales` передаёт при запуске заявки — копия калькуляции на момент запуска."""

    inquiry_id: UUID
    inquiry_number: str
    customer_id: UUID | None
    customer_name: str
    object_name: str
    product_name: str
    template_id: UUID | None
    quantity: Decimal
    manager_id: UUID
    planned_start: date
    due_date: date
    contract_total: Decimal
    labor_cost_planned: Decimal
    operations: Sequence[LaunchOperation] = field(default_factory=tuple)


def get_settings() -> ProductionSettings:
    settings, _ = ProductionSettings.objects.get_or_create()
    return settings


def _default_responsibles(manager_id: UUID) -> dict[OrderStage, UUID | None]:
    settings = get_settings()
    return {
        OrderStage.LAUNCH: settings.launch_responsible_id,
        OrderStage.PREP: settings.prep_responsible_id,
        OrderStage.PROD: settings.prod_responsible_id,
        OrderStage.QC: settings.qc_responsible_id,
        OrderStage.DONE: manager_id,
    }


def _validate_launch(data: LaunchData) -> dict[UUID, WorkCenter]:
    if data.quantity <= 0:
        raise InvalidLaunchData("Количество должно быть больше нуля.")
    if not data.operations:
        raise InvalidLaunchData("В калькуляции нет операций — запускать нечего.")
    ensure_active_employee(data.manager_id)
    if (
        data.template_id is not None
        and not ProductTemplate.objects.filter(id=data.template_id).exists()
    ):
        raise TemplateNotFound
    centers = WorkCenter.objects.in_bulk({op.work_center_id for op in data.operations})
    if len(centers) != len({op.work_center_id for op in data.operations}):
        raise WorkCenterNotFound
    count = len(data.operations)
    edges = []
    for index, op in enumerate(data.operations):
        for pred in op.predecessor_indexes:
            if not 0 <= pred < count or pred == index:
                raise InvalidLaunchData("Связь операций калькуляции ссылается мимо списка.")
            edges.append(ScheduleEdge(_index_id(pred), _index_id(index)))
    if find_cycle([_index_id(i) for i in range(count)], edges) is not None:
        raise InvalidLaunchData("Связи операций калькуляции образуют цикл.")
    return centers


def _index_id(index: int) -> UUID:
    return UUID(int=index + 1)


def create_order_from_inquiry(data: LaunchData, *, actor_id: UUID) -> UUID:
    """Заказ из заявки (§3.2, «Запуск»): копия операций со связями, визы этапов с
    ответственными по умолчанию, план прямым проходом без «не раньше сегодня» и
    `production.order_launched` — всё в транзакции вызывающего (`sales.launch_inquiry`).
    Идемпотентно по заявке: повторный вызов возвращает существующий заказ."""

    existing = ProductionOrder.objects.filter(inquiry_id=data.inquiry_id).first()
    if existing is not None:
        return existing.id
    centers = _validate_launch(data)
    author = org.get_employee_by_user(actor_id)
    with transaction.atomic(), actor_context(actor_id):
        order = ProductionOrder.objects.create(
            number=numbering.issue_number(NUMERATOR_CODE),
            inquiry_id=data.inquiry_id,
            inquiry_number=data.inquiry_number,
            customer_id=data.customer_id,
            customer_name=data.customer_name,
            object_name=data.object_name,
            product_name=data.product_name,
            template_id=data.template_id,
            quantity=data.quantity,
            manager_id=data.manager_id,
            planned_start=data.planned_start,
            due_date=data.due_date,
            contract_total=data.contract_total,
            labor_cost_planned=data.labor_cost_planned,
        )
        OrderStageApproval.objects.bulk_create(
            [
                OrderStageApproval(order=order, stage=stage, responsible_id=responsible)
                for stage, responsible in _default_responsibles(data.manager_id).items()
            ]
        )
        operations = Operation.objects.bulk_create(
            [
                Operation(
                    order=order,
                    seq=op.seq,
                    name=op.name,
                    work_center_id=op.work_center_id,
                    hours=op.hours,
                    people=max(1, op.people),
                    responsible_id=centers[op.work_center_id].responsible_id,
                    not_before=op.not_before,
                )
                for op in data.operations
            ]
        )
        OperationDependency.objects.bulk_create(
            [
                OperationDependency(predecessor=operations[pred], successor=operations[index])
                for index, op in enumerate(data.operations)
                for pred in op.predecessor_indexes
            ]
        )
        reschedule(order, clamp_today=False)
        journal(
            order,
            JournalKind.STAGE,
            f"Создан производственный заказ {order.number}, запуск {fmt_date(order.planned_start)}",
            author_id=author.id if author else None,
            stage=OrderStage.LAUNCH,
        )
        publish(
            OrderLaunched(
                aggregate_id=order.id,
                inquiry_id=order.inquiry_id,
                planned_start=order.planned_start,
            )
        )
    return order.id


def _stage_label(stage: str) -> str:
    return str(OrderStage(stage).label)


def _open_operations_text(operations: Sequence[Operation]) -> str:
    return ", ".join(f"«{op.name}»" for op in operations)


def _check_forward_requirements(order: ProductionOrder, to: OrderStage) -> None:
    """`checkMove` прототипа (§3.1): что должно быть выполнено для перехода вперёд."""

    if to == OrderStage.PREP:
        return
    operations = list(
        Operation.objects.filter(order=order).select_related("work_center").order_by("seq")
    )
    open_ops = [op for op in operations if op.status != OperationStatus.DONE]
    if to == OrderStage.PROD:
        blocking = [op for op in open_ops if op.work_center.phase == WorkPhase.PREP]
        if blocking:
            raise StageRequirementsNotMet(
                f"Подготовка не закрыта визами: {_open_operations_text(blocking)}."
            )
        if not selectors.order_has_kd(order.id):
            raise StageRequirementsNotMet(
                "Подготовка не закрывается без КД: приложите документ вида «КД» или «Чертёж»."
            )
    elif to == OrderStage.QC:
        blocking = [op for op in open_ops if op.work_center.phase != WorkPhase.QC]
        if blocking:
            raise StageRequirementsNotMet(f"Не закрыты визами: {_open_operations_text(blocking)}.")
    elif to == OrderStage.DONE and open_ops:
        raise StageRequirementsNotMet(f"Не закрыты визами: {_open_operations_text(open_ops)}.")


def _approve(
    approval: OrderStageApproval, approver_id: UUID, comment: str, order: ProductionOrder
) -> None:
    approval.approved_by_id = approver_id
    approval.approved_at = timezone.now()
    approval.comment = comment
    approval.save(update_fields=["approved_by", "approved_at", "comment", "updated_at"])
    text = f"Этап «{_stage_label(approval.stage)}» завизирован"
    if approval.responsible_id is not None and approval.responsible_id != approver_id:
        responsible = get_employee(approval.responsible_id)
        text += f" за ответственного {responsible.full_name if responsible else ''}"
    journal(
        order,
        JournalKind.VISA,
        text + (f": {comment}" if comment else ""),
        author_id=approver_id,
        stage=approval.stage,
    )


def approve_order_stage(
    order_id: UUID, stage: OrderStage, *, actor_id: UUID, approver_id: UUID, comment: str = ""
) -> None:
    """Виза текущего этапа заказа. Кто вправе — проверяет API (ответственный или
    начальник производства за него)."""

    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        if order.stage != stage or stage == OrderStage.DONE:
            raise StageRequirementsNotMet("Визируется только текущий этап заказа.")
        approval = OrderStageApproval.objects.select_for_update().get(order=order, stage=stage)
        if approval.approved_at is not None:
            raise AlreadyApproved
        _approve(approval, approver_id, comment.strip(), order)


def move_order_stage(
    order_id: UUID,
    to: OrderStage,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
    comment: str = "",
    may_approve: bool = False,
) -> None:
    """Переход этапа (§3.1): только на соседний; вперёд — после визы текущего этапа
    (нет визы, но `may_approve` — виза ставится в той же транзакции); назад — с
    причиной, виза целевого этапа снимается. `production.order_stage_changed` — в той
    же транзакции (И4)."""

    comment = comment.strip()
    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        current = OrderStage(order.stage)
        distance = ORDER_STAGE_SEQUENCE.index(to) - ORDER_STAGE_SEQUENCE.index(current)
        if distance == 0:
            raise StageSkip("Заказ уже на этом этапе.")
        if abs(distance) > 1:
            raise StageSkip(
                "Вернуть можно только на один этап назад."
                if distance < 0
                else "Этапы проходятся по порядку — перескочить нельзя."
            )
        if distance < 0:
            if not comment:
                raise ReasonRequired("Укажите причину возврата.")
            with invalid_transition_as():
                getattr(order, _BACKWARD[current])()
            order.shipped_at = None
            order.save(update_fields=["stage", "shipped_at", "updated_at"])
            OrderStageApproval.objects.filter(order=order, stage=to).update(
                approved_by=None, approved_at=None, comment=""
            )
            text = f"Возврат: {_stage_label(current)} → {_stage_label(to)}. {comment}"
        else:
            _check_forward_requirements(order, to)
            approval = OrderStageApproval.objects.select_for_update().get(
                order=order, stage=current
            )
            if approval.approved_at is None:
                if not may_approve or actor_employee_id is None:
                    responsible = (
                        get_employee(approval.responsible_id) if approval.responsible_id else None
                    )
                    raise VisaRequired(
                        f"Этап «{_stage_label(current)}» не завизирован. Перевести заказ дальше"
                        f" можно после визы ответственного"
                        f"{': ' + responsible.full_name if responsible else ''}."
                    )
                _approve(approval, actor_employee_id, comment, order)
            with invalid_transition_as():
                getattr(order, _FORWARD[current])()
            if to == OrderStage.DONE:
                order.shipped_at = timezone.now()
            order.save(update_fields=["stage", "shipped_at", "updated_at"])
            text = f"Этап: {_stage_label(current)} → {_stage_label(to)}"
        journal(order, JournalKind.STAGE, text, author_id=actor_employee_id, stage=to)
        publish(OrderStageChanged(aggregate_id=order.id, from_stage=current, to_stage=to))


def set_stage_responsible(
    order_id: UUID,
    stage: OrderStage,
    responsible_id: UUID,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    ensure_active_employee(responsible_id)
    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        if order.stage == OrderStage.DONE:
            raise OrderClosed
        approval = OrderStageApproval.objects.select_for_update().get(order=order, stage=stage)
        old = get_employee(approval.responsible_id) if approval.responsible_id else None
        new = get_employee(responsible_id)
        approval.responsible_id = responsible_id
        approval.save(update_fields=["responsible", "updated_at"])
        journal(
            order,
            JournalKind.PLAN,
            f"Ответственный за этап «{_stage_label(stage)}»: "
            f"{old.full_name if old else '—'} → {new.full_name if new else '—'}",
            author_id=actor_employee_id,
            stage=stage,
        )


def update_order(
    order_id: UUID,
    *,
    due_date: date,
    manager_id: UUID,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    """Срок по договору и менеджер. Менеджер — ответственный за этап «Отгружено»,
    поэтому меняется вместе с ним, если этот этап ещё не завизирован."""

    ensure_active_employee(manager_id)
    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        if order.stage == OrderStage.DONE:
            raise OrderClosed
        changes = []
        if order.due_date != due_date:
            changes.append(f"срок {fmt_date(order.due_date)} → {fmt_date(due_date)}")
            order.due_date = due_date
        if order.manager_id != manager_id:
            new = get_employee(manager_id)
            changes.append(f"менеджер → {new.full_name if new else '—'}")
            order.manager_id = manager_id
            OrderStageApproval.objects.filter(
                order=order, stage=OrderStage.DONE, approved_at__isnull=True
            ).update(responsible_id=manager_id)
        if not changes:
            return
        order.save(update_fields=["due_date", "manager", "updated_at"])
        journal(
            order,
            JournalKind.PLAN,
            "Изменено: " + ", ".join(changes),
            author_id=actor_employee_id,
        )


def shift_order(
    order_id: UUID, days: int, *, actor_id: UUID, actor_employee_id: UUID | None
) -> None:
    """Сдвиг всего заказа на Ганте (`bindGantt`, режим «all»): дата запуска и «не ранее»
    всех не начатых операций — на `days` рабочих дней, затем пересчёт."""

    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        if order.stage == OrderStage.DONE:
            raise OrderClosed
        if days == 0:
            return
        order.planned_start = add_working_days(order.planned_start, days)
        order.save(update_fields=["planned_start", "updated_at"])
        waiting = list(
            Operation.objects.filter(
                order=order, status=OperationStatus.WAIT, not_before__isnull=False
            )
        )
        for op in waiting:
            assert op.not_before is not None
            op.not_before = add_working_days(op.not_before, days)
        Operation.objects.bulk_update(waiting, ["not_before"])
        reschedule(order)
        finish = selectors.order_planned_finish(order.id)
        journal(
            order,
            JournalKind.PLAN,
            f"План заказа сдвинут на {days:+d} раб. дн., окончание {fmt_date(finish)}",
            author_id=actor_employee_id,
        )


def replan_order(
    order_id: UUID,
    planned_start: date | None,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    """«Пересчитать план» на вкладке плана: новая дата запуска (если задана) и прямой
    проход. Начатые операции стоят по факту."""

    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        if order.stage == OrderStage.DONE:
            raise OrderClosed
        if planned_start is not None and planned_start != order.planned_start:
            order.planned_start = planned_start
            order.save(update_fields=["planned_start", "updated_at"])
        reschedule(order)
        finish = selectors.order_planned_finish(order.id)
        journal(
            order,
            JournalKind.PLAN,
            f"План пересчитан с {fmt_date(order.planned_start)}, окончание {fmt_date(finish)}",
            author_id=actor_employee_id,
        )
