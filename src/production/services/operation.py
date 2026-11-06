"""Операции заказа: ход выполнения, виза, автостарт, откат, правка плана и связей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, «Операции»; прототип `opDialog`,
`opVisa`, `autoStart`, `bindGantt`).

Любая правка блокирует заказ (`lock_order`). Права — в API: кто ответственный, кто
вправе визировать за другого. Сервис получает сотрудника, от чьего имени действие
(`actor_employee_id`), и пишет его в отметки и журнал.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.common.scheduling import ScheduleEdge, find_cycle, next_working_day
from src.core.events.publisher import publish
from src.production import selectors
from src.production.events import OperationApproved
from src.production.exceptions import (
    CannotMoveEarlier,
    DependencyCycle,
    DependencyInvalid,
    InspectionRequired,
    InvalidProgress,
    InvalidTransition,
    OperationNotWaiting,
    OrderClosed,
    OrderNotInWork,
    PeopleOverCapacity,
    PredecessorsNotDone,
    SupplyHasNoProgress,
    invalid_transition_as,
)
from src.production.models import (
    JournalKind,
    Operation,
    OperationDependency,
    OperationStatus,
    OrderStage,
    ProductionOrder,
)
from src.production.models.operation import PROGRESS_STEPS
from src.production.planning import finish_of
from src.production.services.common import (
    earn_to,
    ensure_active_employee,
    fmt_date,
    get_employee,
    journal,
    lock_operation,
    reschedule,
)
from src.quality import facade as quality

WORK_STAGES = (OrderStage.PREP, OrderStage.PROD, OrderStage.QC)


def _ensure_in_work(order: ProductionOrder) -> None:
    if order.stage not in WORK_STAGES:
        raise OrderNotInWork


def _ensure_plannable(order: ProductionOrder, operation: Operation) -> None:
    if order.stage == OrderStage.DONE:
        raise OrderClosed
    if operation.status != OperationStatus.WAIT:
        raise OperationNotWaiting


def _open_predecessors(operation: Operation) -> list[Operation]:
    return list(
        Operation.objects.filter(successor_links__successor=operation)
        .exclude(status=OperationStatus.DONE)
        .order_by("seq")
    )


def _ensure_predecessors_done(operation: Operation, prefix: str) -> None:
    open_preds = _open_predecessors(operation)
    if open_preds:
        names = ", ".join(f"«{op.name}»" for op in open_preds)
        raise PredecessorsNotDone(f"{prefix}: не закрыты {names}.")


def _start(operation: Operation, started_by: UUID | None) -> None:
    with invalid_transition_as("Начать можно только операцию, которая ожидает."):
        operation.mark_started()
    operation.started_at = timezone.now()
    operation.started_by_id = started_by
    operation.save(update_fields=["status", "started_at", "started_by", "updated_at"])


def _submit(operation: Operation) -> None:
    earn_to(operation, 100)
    with invalid_transition_as("На визу передаётся операция в работе."):
        operation.mark_submitted()
    operation.progress = 100
    operation.save(update_fields=["status", "progress", "updated_at"])


def _reset(operation: Operation) -> None:
    earn_to(operation, 0)
    with invalid_transition_as("Откатить можно операцию в работе или на визе."):
        operation.mark_reset()
    operation.progress = 0
    operation.started_at = None
    operation.started_by = None
    operation.save(update_fields=["status", "progress", "started_at", "started_by", "updated_at"])


def set_operation_status(
    operation_id: UUID,
    status: OperationStatus,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    """Статус из карточки операции (`odS` прототипа): «ожидает» — откат с обнулением
    прогресса и сторно освоения; «в работе» — старт (предшественники закрыты) или
    возврат с визы; «на визе» — 100 % и передача ответственному. «Выполнено» — только
    виза (`approve_operation`)."""

    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_in_work(order)
        current = operation.status
        if status == current:
            return
        if status == OperationStatus.DONE or current == OperationStatus.DONE:
            raise InvalidTransition("Выполненной операция становится только по визе.")
        if status == OperationStatus.WAIT:
            _reset(operation)
        else:
            if current == OperationStatus.WAIT:
                _ensure_predecessors_done(operation, "Нельзя начать")
                _start(operation, actor_employee_id)
            if status == OperationStatus.WORK and current == OperationStatus.CHECK:
                with invalid_transition_as():
                    operation.mark_returned()
                operation.save(update_fields=["status", "updated_at"])
            if status == OperationStatus.CHECK:
                _submit(operation)
        journal(
            order,
            JournalKind.STATUS,
            f"Статус: {OperationStatus(status).label}",
            operation=operation,
            author_id=actor_employee_id,
        )


def set_operation_progress(
    operation_id: UUID, progress: int, *, actor_id: UUID, actor_employee_id: UUID | None
) -> None:
    """Прогресс операции в работе 0…100 с шагом 10; освоение дописывается приращением;
    100 % — операция уходит на визу ответственному."""

    if progress not in PROGRESS_STEPS:
        raise InvalidProgress
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_in_work(order)
        if operation.work_center.is_supply:
            raise SupplyHasNoProgress
        if operation.status != OperationStatus.WORK:
            raise InvalidTransition("Процент выполнения меняется у операции в работе.")
        if progress == operation.progress:
            return
        if progress == 100:
            _submit(operation)
            responsible = (
                get_employee(operation.responsible_id) if operation.responsible_id else None
            )
            text = "Выполнено 100%, передано на визу" + (
                f" {responsible.full_name}" if responsible else ""
            )
        else:
            earn_to(operation, progress)
            operation.progress = progress
            operation.save(update_fields=["progress", "updated_at"])
            text = f"Выполнено {progress}%"
        journal(order, JournalKind.STATUS, text, operation=operation, author_id=actor_employee_id)


def approve_operation(
    operation_id: UUID, *, actor_id: UUID, approver_id: UUID, comment: str = ""
) -> None:
    """Виза операции (`opVisa`): предшественники закрыты, есть запись контроля, если
    у участка есть точка контроля; прогресс 100, освоение до полного, `done`; затем
    автостарт последователей. Кто вправе — проверяет API; если визирует не
    ответственный (начальник производства), это пишется в `approved_for`."""

    comment = comment.strip()
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_in_work(order)
        if operation.status not in (OperationStatus.WORK, OperationStatus.CHECK):
            raise InvalidTransition("Визируется операция в работе или на визе.")
        _ensure_predecessors_done(operation, "Сначала должны быть закрыты предшествующие")
        if quality.requires_inspection(operation.work_center_id) and not quality.has_inspection(
            operation.id
        ):
            raise InspectionRequired
        earn_to(operation, 100)
        with invalid_transition_as():
            operation.mark_approved()
        operation.progress = 100
        operation.approved_at = timezone.now()
        operation.approved_by_id = approver_id
        if operation.responsible_id is not None and operation.responsible_id != approver_id:
            operation.approved_for_id = operation.responsible_id
        operation.save(
            update_fields=[
                "status",
                "progress",
                "approved_at",
                "approved_by",
                "approved_for",
                "updated_at",
            ]
        )
        text = "Выполнено. Виза ответственного"
        if operation.approved_for_id is not None:
            responsible = get_employee(operation.approved_for_id)
            text = (
                f"Выполнено. Виза за ответственного {responsible.full_name if responsible else ''}"
            )
        journal(
            order,
            JournalKind.VISA,
            text + (f": {comment}" if comment else ""),
            operation=operation,
            author_id=approver_id,
        )
        publish(
            OperationApproved(
                aggregate_id=operation.id,
                order_id=order.id,
                work_center_id=operation.work_center_id,
            )
        )
        autostart(order)


def autostart(order: ProductionOrder) -> list[UUID]:
    """`autoStart` прототипа: операции, у которых закрыты все предшественники и
    наступила плановая дата, — в работу, с записью «система». Вызывается внутри
    транзакции сервиса, заказ уже заблокирован."""

    if order.stage not in WORK_STAGES:
        return []
    today = timezone.localdate()
    candidates = list(
        Operation.objects.filter(order=order, status=OperationStatus.WAIT, planned_start__lte=today)
        .exclude(
            predecessor_links__predecessor__status__in=[
                OperationStatus.WAIT,
                OperationStatus.WORK,
                OperationStatus.CHECK,
            ]
        )
        .order_by("seq")
    )
    for operation in candidates:
        _start(operation, None)
        journal(
            order,
            JournalKind.STATUS,
            "Предшественники закрыты — операция доступна для работы",
            operation=operation,
        )
    return [op.id for op in candidates]


def set_operation_responsible(
    operation_id: UUID,
    responsible_id: UUID,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    ensure_active_employee(responsible_id)
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        if order.stage == OrderStage.DONE:
            raise OrderClosed
        if operation.status == OperationStatus.DONE:
            raise InvalidTransition("У выполненной операции ответственный не меняется.")
        old = get_employee(operation.responsible_id) if operation.responsible_id else None
        new = get_employee(responsible_id)
        operation.responsible_id = responsible_id
        operation.save(update_fields=["responsible", "updated_at"])
        journal(
            order,
            JournalKind.PLAN,
            f"Ответственный: {old.full_name if old else '—'} → {new.full_name if new else '—'}",
            operation=operation,
            author_id=actor_employee_id,
        )


def set_operation_people(
    operation_id: UUID, people: int, *, actor_id: UUID, actor_employee_id: UUID | None
) -> None:
    """Исполнителей — от 1 до мощности участка, только у не начатой операции."""

    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_plannable(order, operation)
        center = operation.work_center
        if people < 1 or (not center.is_supply and people > center.capacity):
            raise PeopleOverCapacity(
                f"Исполнителей — от 1 до {center.capacity} (мощность участка «{center.name}»)."
            )
        operation.people = people
        operation.save(update_fields=["people", "updated_at"])
        reschedule(order)
        journal(
            order,
            JournalKind.PLAN,
            f"Исполнителей: {people}, окончание заказа "
            f"{fmt_date(selectors.order_planned_finish(order.id))}",
            operation=operation,
            author_id=actor_employee_id,
        )


def set_operation_not_before(
    operation_id: UUID,
    not_before: date | None,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_plannable(order, operation)
        operation.not_before = next_working_day(not_before) if not_before else None
        operation.save(update_fields=["not_before", "updated_at"])
        reschedule(order)
        operation.refresh_from_db(fields=["planned_start"])
        journal(
            order,
            JournalKind.PLAN,
            f"Не ранее: {fmt_date(operation.not_before) if operation.not_before else 'снято'}, "
            f"начало {fmt_date(operation.planned_start)}",
            operation=operation,
            author_id=actor_employee_id,
        )


def move_operation(
    operation_id: UUID, start: date, *, actor_id: UUID, actor_employee_id: UUID | None
) -> None:
    """Перенос полосы операции на Ганте: `not_before := новая дата`, пересчёт. Если
    раньше нельзя — ошибка с названием мешающей операции, изменений нет."""

    want = next_working_day(start)
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_plannable(order, operation)
        operation.not_before = want
        operation.save(update_fields=["not_before", "updated_at"])
        reschedule(order)
        operation.refresh_from_db(fields=["planned_start"])
        assert operation.planned_start is not None
        if operation.planned_start > want:
            raise CannotMoveEarlier(
                f"Раньше {fmt_date(operation.planned_start)} нельзя: операция ждёт "
                f"{_blocker_text(order, operation)}."
            )
        journal(
            order,
            JournalKind.PLAN,
            f"Перенесена на {fmt_date(operation.planned_start)}; окончание заказа "
            f"{fmt_date(selectors.order_planned_finish(order.id))}",
            operation=operation,
            author_id=actor_employee_id,
        )


def _blocker_text(order: ProductionOrder, operation: Operation) -> str:
    predecessors = list(
        Operation.objects.filter(successor_links__successor=operation).select_related("work_center")
    )
    finishes = [(finish_of(p), p) for p in predecessors]
    dated = [(f, p) for f, p in finishes if f is not None]
    if dated:
        latest = max(dated, key=lambda pair: pair[0])[1]
        return f"«{latest.name}»"
    if operation.planned_start == timezone.localdate():
        return "сегодняшнего дня"
    return "начала заказа"


def set_predecessors(
    operation_id: UUID,
    predecessor_ids: Sequence[UUID],
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> None:
    """Предшественники операции целиком (колонка «Предш.» вкладки плана). Только у не
    начатой операции; цикл проверяется обходом графа заказа под блокировкой заказа;
    что все операции одного заказа — дублирует триггер БД."""

    wanted = list(dict.fromkeys(predecessor_ids))
    with transaction.atomic(), actor_context(actor_id):
        order, operation = lock_operation(operation_id)
        _ensure_plannable(order, operation)
        if operation.id in wanted:
            raise DependencyInvalid("Операция не может зависеть от самой себя.")
        siblings = {op.id: op for op in Operation.objects.filter(order=order).order_by("seq")}
        if any(pred_id not in siblings for pred_id in wanted):
            raise DependencyInvalid
        other_edges = [
            ScheduleEdge(dep.predecessor_id, dep.successor_id)
            for dep in OperationDependency.objects.filter(successor__order=order).exclude(
                successor=operation
            )
        ]
        new_edges = [ScheduleEdge(pred_id, operation.id) for pred_id in wanted]
        if find_cycle(siblings.keys(), other_edges + new_edges) is not None:
            raise DependencyCycle
        OperationDependency.objects.filter(successor=operation).delete()
        OperationDependency.objects.bulk_create(
            [OperationDependency(predecessor_id=pred_id, successor=operation) for pred_id in wanted]
        )
        reschedule(order)
        numbers = ", ".join(str(siblings[pred_id].seq) for pred_id in wanted) or "нет"
        journal(
            order,
            JournalKind.PLAN,
            f"Предшественники: {numbers}",
            operation=operation,
            author_id=actor_employee_id,
        )
