"""Доменные исключения модуля «Табель». `ValidationError` → 400 (неверный ввод),
`ConflictError` → 409 (состояние периода не позволяет действие)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django_fsm import TransitionNotAllowed

from src.core.common.exceptions import ConflictError, ValidationError


class InvalidTransition(ConflictError):
    code = "invalid_transition"
    default_message = "Переход табеля недопустим из текущего статуса."


@contextmanager
def invalid_transition_as(message: str | None = None) -> Iterator[None]:
    """django-fsm `TransitionNotAllowed` → доменный `InvalidTransition` (409, а не 500)."""

    try:
        yield
    except TransitionNotAllowed as exc:
        raise InvalidTransition(message) from exc


class InvalidMonth(ValidationError):
    code = "invalid_month"
    default_message = "Месяц табеля задаётся первым числом."


class PeriodLocked(ConflictError):
    code = "period_locked"
    default_message = (
        "Табель за этот месяц не открыт для правки. Для корректировки период открывают "
        "с новой версией."
    )


class NotAWorker(ValidationError):
    code = "not_a_worker"
    default_message = "У сотрудника нет профиля работника — табель на него не ведётся."


class EmployeeNotFound(ValidationError):
    code = "employee_not_found"
    default_message = "Сотрудник не найден."


class TimeCodeNotFound(ValidationError):
    code = "time_code_not_found"
    default_message = "Нет такого кода вида времени."


class InvalidAllocation(ValidationError):
    code = "invalid_allocation"
    default_message = "Строка разноски заполнена неверно."


class DayLimitExceeded(ValidationError):
    code = "day_limit_exceeded"
    default_message = "Больше 24 часов в день."


class BlockingChecks(ConflictError):
    code = "blocking_checks"
    default_message = "Есть блокирующие замечания — табель нельзя подать на согласование."


class ManagerConfirmationsMissing(ConflictError):
    code = "manager_confirmations_missing"
    default_message = "Ждём подтверждения часов руководителями проектов."


class NothingToConfirm(ConflictError):
    code = "nothing_to_confirm"
    default_message = "В табеле нет часов по заказам этого менеджера, или они уже подтверждены."


class ReasonRequired(ValidationError):
    code = "reason_required"
    default_message = "Причина обязательна."
