"""Доменные исключения модуля «Оборудование и ТО».

Подклассы `DomainError` (`src/core/common/exceptions.py`): API отдаёт их как 400/409,
а не как 500. `code` — для ветвления фронтенда.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django_fsm import TransitionNotAllowed

from src.core.common.exceptions import ConflictError, ValidationError


class InvalidTransition(ConflictError):
    code = "invalid_transition"
    default_message = "Переход статуса недопустим из текущего состояния."


@contextmanager
def invalid_transition_as(message: str | None = None) -> Iterator[None]:
    """django-fsm `TransitionNotAllowed` → доменный `InvalidTransition` (409)."""

    try:
        yield
    except TransitionNotAllowed as exc:
        raise InvalidTransition(message) from exc


class InventoryNoTaken(ConflictError):
    code = "inventory_no_taken"
    default_message = "Оборудование с таким инвентарным номером уже есть."


class MaintenanceCodeTaken(ConflictError):
    code = "maintenance_code_taken"
    default_message = "Такой вид ТО у оборудования уже есть."


class InvalidHours(ValidationError):
    code = "invalid_hours"
    default_message = "Часы не могут быть отрицательными."


class DayOverflow(ValidationError):
    code = "day_overflow"
    default_message = "Больше 24 ч в сутки."


class ReasonRequired(ValidationError):
    code = "reason_required"
    default_message = "Укажите причину."


class FutureDate(ValidationError):
    code = "future_date"
    default_message = "Наработку за будущие сутки внести нельзя."


class ReferenceNotFound(ValidationError):
    code = "reference_not_found"
    default_message = "Значение справочника не найдено или не действует."


class EmployeeNotFound(ValidationError):
    code = "employee_not_found"
    default_message = "Сотрудник не найден среди работающих."


class DescriptionRequired(ValidationError):
    code = "description_required"
    default_message = "Опишите, что произошло."


class MaintenanceTypeMismatch(ValidationError):
    code = "maintenance_type_mismatch"
    default_message = (
        "Вид ТО указывается у записи вида «ТО» и должен относиться к этому оборудованию."
    )


class FinishBeforeStart(ValidationError):
    code = "finish_before_start"
    default_message = "Окончание простоя раньше начала."


class RepairClosed(ConflictError):
    code = "repair_closed"
    default_message = "Закрытая запись не правится: часы уже переданы в табель."


class CloseRequirementsNotMet(ValidationError):
    code = "close_requirements_not_met"
    default_message = "Запись не готова к закрытию."


class DuplicateWorker(ValidationError):
    code = "duplicate_worker"
    default_message = "Сотрудник указан в ремонте дважды."
