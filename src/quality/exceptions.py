"""Доменные исключения модуля «ОТК и качество».

Подклассы `DomainError` (`src/core/common/exceptions.py`): API отдаёт их как 400/409
с `{"code", "message"}`, а не как 500.
"""

from __future__ import annotations

from src.core.common.exceptions import ConflictError, ValidationError


class ActorNotEmployee(ValidationError):
    code = "actor_not_employee"
    default_message = "Текущий пользователь не связан с сотрудником."


class OperationNotFound(ValidationError):
    code = "operation_not_found"
    default_message = "Операция не найдена."


class NoInspectionPoint(ConflictError):
    code = "no_inspection_point"
    default_message = "Для этого участка точка контроля не предусмотрена."


class OrderNotLaunched(ConflictError):
    code = "order_not_launched"
    default_message = "Запись результатов доступна после запуска заказа в производство."


class InvalidCounts(ValidationError):
    code = "invalid_counts"
    default_message = "Укажите количество проверенных; брака не больше, чем проверено."


class DefectNotClassified(ValidationError):
    code = "defect_not_classified"
    default_message = "Для брака укажите вид дефекта и причину."


class ReferenceNotFound(ValidationError):
    code = "reference_not_found"
    default_message = "Значение справочника не найдено или не действует."


class FutureDate(ValidationError):
    code = "future_date"
    default_message = "Результат контроля за будущую дату записать нельзя."
