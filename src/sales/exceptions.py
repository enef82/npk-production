"""Доменные исключения модуля «Заявки и калькуляция» — подклассы `DomainError`:
`ValidationError` → 400, `ConflictError` → 409."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django_fsm import TransitionNotAllowed

from src.core.common.exceptions import ConflictError, ValidationError


class InvalidTransition(ConflictError):
    code = "invalid_transition"
    default_message = "Переход недопустим из текущего этапа заявки."


@contextmanager
def invalid_transition_as(message: str | None = None) -> Iterator[None]:
    try:
        yield
    except TransitionNotAllowed as exc:
        raise InvalidTransition(message) from exc


class EmployeeNotFound(ValidationError):
    code = "employee_not_found"
    default_message = "Сотрудник не найден среди работающих."


class CustomerRequired(ValidationError):
    code = "customer_required"
    default_message = "Укажите заказчика: выберите контрагента или введите нового."


class CustomerNotFound(ValidationError):
    code = "customer_not_found"
    default_message = "Контрагент не найден."


class WorkCenterNotFound(ValidationError):
    code = "work_center_not_found"
    default_message = "Участок не найден."


class TemplateNotFound(ValidationError):
    code = "template_not_found"
    default_message = "Шаблон изделия не найден."


class InvalidValues(ValidationError):
    code = "invalid_values"
    default_message = "Значения калькуляции некорректны."


class InquiryClosed(ConflictError):
    code = "inquiry_closed"
    default_message = "Заявка запущена или проиграна — правка невозможна."


class StageSkip(ConflictError):
    code = "stage_skip"
    default_message = "Этапы проходятся по порядку — переход только на соседний этап."


class StageRequirementsNotMet(ConflictError):
    code = "stage_requirements_not_met"
    default_message = "Условия перехода на этап не выполнены."


class VisaRequired(ConflictError):
    code = "visa_required"
    default_message = "Перевести дальше можно после визы ответственного за этап."


class AlreadyApproved(ConflictError):
    code = "already_approved"
    default_message = "Виза уже поставлена."


class ReasonRequired(ValidationError):
    code = "reason_required"
    default_message = "Причина обязательна."


class DependencyInvalid(ValidationError):
    code = "dependency_invalid"
    default_message = "Связать можно две разные операции одной калькуляции."


class DependencyCycle(ConflictError):
    code = "dependency_cycle"
    default_message = "Циклическая зависимость — такая связь невозможна."


class LossReasonNotFound(ValidationError):
    code = "loss_reason_not_found"
    default_message = "Причина проигрыша не найдена."
