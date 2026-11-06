"""Доменные исключения модуля «Производство».

Подклассы `DomainError` (`src/core/common/exceptions.py`): обработчик API отдаёт их как
400/409 с `{"code", "message"}`. `ValidationError` → 400 (некорректный вход),
`ConflictError` → 409 (состояние заказа или операции не позволяет действие).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django_fsm import TransitionNotAllowed

from src.core.common.exceptions import ConflictError, ValidationError


class InvalidTransition(ConflictError):
    code = "invalid_transition"
    default_message = "Переход недопустим из текущего состояния."


@contextmanager
def invalid_transition_as(message: str | None = None) -> Iterator[None]:
    """django-fsm `TransitionNotAllowed` → доменный `InvalidTransition` (409, а не 500)."""

    try:
        yield
    except TransitionNotAllowed as exc:
        raise InvalidTransition(message) from exc


class ActorNotEmployee(ValidationError):
    code = "actor_not_employee"
    default_message = "Текущий пользователь не связан с сотрудником."


class EmployeeNotFound(ValidationError):
    code = "employee_not_found"
    default_message = "Сотрудник не найден среди работающих."


class WorkCenterNotFound(ValidationError):
    code = "work_center_not_found"
    default_message = "Участок не найден или выведен из работы."


class TemplateNotFound(ValidationError):
    code = "template_not_found"
    default_message = "Шаблон изделия не найден."


class InvalidLaunchData(ValidationError):
    code = "invalid_launch_data"
    default_message = "Данные запуска некорректны."


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


class OrderClosed(ConflictError):
    code = "order_closed"
    default_message = "Заказ отгружен — план и операции не правятся."


class OrderNotInWork(ConflictError):
    code = "order_not_in_work"
    default_message = (
        "Ход операций ведётся на этапах «Подготовка», «Изготовление» и «ОТК и испытания»."
    )


class OperationNotWaiting(ConflictError):
    code = "operation_not_waiting"
    default_message = "План меняется только у операции, которая ещё не начата."


class PredecessorsNotDone(ConflictError):
    code = "predecessors_not_done"
    default_message = "Сначала должны быть закрыты предшествующие операции."


class InspectionRequired(ConflictError):
    code = "inspection_required"
    default_message = "Нет записи контроля — зафиксируйте результат проверки в карточке операции."


class InvalidProgress(ValidationError):
    code = "invalid_progress"
    default_message = "Выполнение — от 0 до 100 % с шагом 10."


class SupplyHasNoProgress(ConflictError):
    code = "supply_has_no_progress"
    default_message = "У снабженческой операции нет процента выполнения — только виза."


class PeopleOverCapacity(ValidationError):
    code = "people_over_capacity"
    default_message = "Исполнителей больше, чем мощность участка."


class CannotMoveEarlier(ConflictError):
    code = "cannot_move_earlier"
    default_message = "Раньше операцию поставить нельзя."


class DependencyInvalid(ValidationError):
    code = "dependency_invalid"
    default_message = "Связать можно две разные операции одного заказа."


class DependencyCycle(ConflictError):
    code = "dependency_cycle"
    default_message = "Циклическая зависимость — такая связь невозможна."


class OperationMismatch(ValidationError):
    code = "operation_mismatch"
    default_message = "Операция не принадлежит этому заказу."


class TextRequired(ValidationError):
    code = "text_required"
    default_message = "Текст обязателен."


class DocumentTypeInvalid(ValidationError):
    code = "document_type_invalid"
    default_message = "Недопустимый вид документа заказа."


class DocumentNotLinked(ValidationError):
    code = "document_not_linked"
    default_message = "Документ не привязан к этому заказу."
