"""Табель подразделения за месяц: подача, визы менеджеров, согласование, передача в 1С,
закрытие, переоткрытие с новой версией (`renderTimesheet` прототипа, спецификация §3.5).
Каждый переход пишет строку журнала `TimesheetPeriodEvent` в той же транзакции.

Данные о заказах (`order_managers`, `order_numbers`) — аргументы: их даёт
`production.facade` через `production_link`, табель о заказах не знает.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.timesheet import selectors
from src.timesheet.exceptions import (
    BlockingChecks,
    InvalidMonth,
    InvalidTransition,
    ManagerConfirmationsMissing,
    NothingToConfirm,
    ReasonRequired,
    invalid_transition_as,
)
from src.timesheet.models import (
    PeriodEventKind,
    PeriodStatus,
    TimesheetPeriod,
    TimesheetPeriodEvent,
)

EDITABLE_STATUSES = (PeriodStatus.DRAFT, PeriodStatus.REOPENED)


def ensure_month(month: date) -> None:
    if month.day != 1:
        raise InvalidMonth


def lock_period(department_id: UUID, month: date) -> TimesheetPeriod:
    """Период под `select_for_update`, заводится при первом обращении. Вызывать внутри
    транзакции."""

    ensure_month(month)
    TimesheetPeriod.objects.get_or_create(department_id=department_id, month=month)
    return TimesheetPeriod.objects.select_for_update().get(department_id=department_id, month=month)


def _log(
    period: TimesheetPeriod,
    kind: PeriodEventKind,
    actor_id: UUID | None,
    comment: str = "",
    manager_id: UUID | None = None,
) -> None:
    TimesheetPeriodEvent.objects.create(
        period=period,
        kind=kind,
        version=period.version,
        actor_id=actor_id,
        manager_id=manager_id,
        comment=comment,
    )


def _save_status(period: TimesheetPeriod) -> None:
    period.save(update_fields=["status", "version", "updated_at"])


def submit_period(department_id: UUID, month: date, *, today: date, actor_id: UUID) -> None:
    """`draft`/`reopened` → `on_review`. Блокирующие проверки не дают подать."""

    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        blocking = [
            c for c in selectors.period_checks(department_id, month, today) if c.is_blocking
        ]
        if blocking:
            raise BlockingChecks(details=[c.text for c in blocking])
        with invalid_transition_as("Подать можно только заполняемый табель."):
            period.mark_submitted()
        _save_status(period)
        _log(period, PeriodEventKind.SUBMITTED, actor_id)


def _required_managers(
    department_id: UUID, month: date, order_managers: Mapping[UUID, UUID]
) -> set[UUID]:
    hours = selectors.department_order_hours(department_id, month)
    return set(selectors.manager_hours(hours, order_managers))


def confirm_manager_hours(
    department_id: UUID,
    month: date,
    manager_id: UUID,
    *,
    order_managers: Mapping[UUID, UUID],
    actor_id: UUID,
) -> None:
    """Виза менеджера: часы по его заказам обоснованно легли на заказы. Только на
    согласовании и только если у менеджера есть часы в табеле."""

    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        if period.status != PeriodStatus.ON_REVIEW:
            raise InvalidTransition("Подтверждают часы табеля на согласовании.")
        confirmed = selectors.confirmed_managers(selectors.list_period_events(period.id))
        required = _required_managers(department_id, month, order_managers)
        if manager_id not in required or manager_id in confirmed:
            raise NothingToConfirm
        _log(period, PeriodEventKind.MANAGER_CONFIRMED, actor_id, manager_id=manager_id)


def approve_period(
    department_id: UUID,
    month: date,
    *,
    order_managers: Mapping[UUID, UUID],
    actor_id: UUID,
) -> None:
    """`on_review` → `approved` — экономист, после виз всех менеджеров с часами."""

    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        if period.status == PeriodStatus.ON_REVIEW:
            confirmed = selectors.confirmed_managers(selectors.list_period_events(period.id))
            missing = _required_managers(department_id, month, order_managers) - confirmed
            if missing:
                raise ManagerConfirmationsMissing(details=sorted(str(m) for m in missing))
        with invalid_transition_as("Утвердить можно только табель на согласовании."):
            period.mark_approved()
        _save_status(period)
        _log(period, PeriodEventKind.APPROVED, actor_id)


def return_period(department_id: UUID, month: date, comment: str, *, actor_id: UUID) -> None:
    """Возврат на доработку: в черновик, а после переоткрытия — в «открыт для
    корректировки», чтобы версия не потерялась."""

    comment = comment.strip()
    if not comment:
        raise ReasonRequired
    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        with invalid_transition_as("Вернуть можно только табель на согласовании."):
            if period.version > 1:
                period.mark_returned_to_reopened()
            else:
                period.mark_returned_to_draft()
        _save_status(period)
        _log(period, PeriodEventKind.RETURNED, actor_id, comment)


def send_period(
    department_id: UUID,
    month: date,
    *,
    order_numbers: Mapping[UUID, str],
    actor_id: UUID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """`approved` → `sent`: формирует оба пакета 1С и возвращает их. Транспорт в 1С вне
    объёма (ИС ADR 0002): пакеты скачиваются файлом. Отдельно пакеты не хранятся —
    разноска утверждённого периода заморожена до переоткрытия, а переоткрытие
    поднимает версию, так что пакет версии N всегда собирается заново тем же."""

    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        with invalid_transition_as("Передать в 1С можно только утверждённый табель."):
            period.mark_sent()
        packages = selectors.period_packages(department_id, month, order_numbers)
        assert packages is not None  # период держит подразделение по PROTECT
        timesheet, cost_allocation = packages
        _save_status(period)
        _log(
            period,
            PeriodEventKind.SENT,
            actor_id,
            f"табель {len(timesheet['entries'])} строк, "
            f"база распределения {len(cost_allocation['rows'])} строк",
        )
        return timesheet, cost_allocation


def close_period(department_id: UUID, month: date, *, actor_id: UUID) -> None:
    """`sent` → `closed`: начисления получены из 1С."""

    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        with invalid_transition_as("Закрыть можно только переданный в 1С табель."):
            period.mark_closed()
        _save_status(period)
        _log(period, PeriodEventKind.CLOSED, actor_id)


def reopen_period(department_id: UUID, month: date, comment: str, *, actor_id: UUID) -> None:
    """`sent`/`closed` → `reopened`, версия + 1: после правок период пройдёт согласование
    и уйдёт в 1С целиком заново."""

    comment = comment.strip()
    if not comment:
        raise ReasonRequired
    with transaction.atomic(), actor_context(actor_id):
        period = lock_period(department_id, month)
        with invalid_transition_as(
            "Открыть для корректировки можно переданный или закрытый табель."
        ):
            period.mark_reopened()
        period.version += 1
        _save_status(period)
        _log(period, PeriodEventKind.REOPENED, actor_id, comment)
