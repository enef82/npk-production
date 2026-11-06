"""Доменные исключения модуля «Снабжение и склад».

Подклассы `DomainError` (`src/core/common/exceptions.py`): API отдаёт их как 400/409
с `{"code", "message"}`, а не как 500.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django_fsm import TransitionNotAllowed

from src.core.common.exceptions import ConflictError, ValidationError


class InvalidTransition(ConflictError):
    code = "invalid_transition"
    default_message = "Действие недопустимо в текущем статусе позиции."


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


class LinesRequired(ValidationError):
    code = "lines_required"
    default_message = "Не выбрано ни одной позиции."


class LinesNotFound(ValidationError):
    code = "lines_not_found"
    default_message = "Часть позиций не найдена."


class MixedOrders(ValidationError):
    code = "mixed_orders"
    default_message = "В одну заявку на закупку попадают позиции одного заказа (или склада / ТО)."


class InvalidLine(ValidationError):
    code = "invalid_line"
    default_message = "У позиции должны быть наименование и количество больше нуля."


class OrderNotFound(ValidationError):
    code = "order_not_found"
    default_message = "Производственный заказ не найден."


class OrderClosed(ConflictError):
    code = "order_closed"
    default_message = "Заказ отгружен — потребность не правится."


class OperationMismatch(ValidationError):
    code = "operation_mismatch"
    default_message = "Операция не принадлежит этому заказу."


class SupplierRequired(ValidationError):
    code = "supplier_required"
    default_message = "Укажите поставщика, номер заказа и срок поставки."


class SupplierTaken(ConflictError):
    code = "supplier_taken"
    default_message = "Такой поставщик уже есть."


class ReasonRequired(ValidationError):
    code = "reason_required"
    default_message = "Укажите срок и причину переноса."


class FutureDate(ValidationError):
    code = "future_date"
    default_message = "Дата не может быть позже сегодняшней."


class EmployeeNotFound(ValidationError):
    code = "employee_not_found"
    default_message = "Сотрудник не найден среди работающих."


class SingleLineOnly(ValidationError):
    code = "single_line_only"
    default_message = "Цена и принятое количество указываются только для одной позиции."
