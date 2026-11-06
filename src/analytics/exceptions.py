"""Доменные исключения модуля «Аналитика».

Подклассы `DomainError` (`src/core/common/exceptions.py`): API отдаёт их как 400/409
с `{"code", "message"}`, а не как 500.
"""

from __future__ import annotations

from src.core.common.exceptions import ConflictError, ValidationError


class ActorNotEmployee(ValidationError):
    code = "actor_not_employee"
    default_message = "Текущий пользователь не связан с сотрудником."


class NotMonday(ValidationError):
    code = "not_monday"
    default_message = "Неделя отсечки задаётся понедельником."


class FutureWeek(ConflictError):
    code = "future_week"
    default_message = "Неделя ещё не началась — закрыть отсечку нельзя."


class CutoffAlreadyClosed(ConflictError):
    code = "cutoff_already_closed"
    default_message = "Отсечка этой недели уже закрыта — данные недели не меняются."


class CutoffNotClosed(ConflictError):
    code = "cutoff_not_closed"
    default_message = "Отсечка этой недели не закрыта."


class ReasonRequired(ValidationError):
    code = "reason_required"
    default_message = "Укажите причину переоткрытия отсечки."


class InvalidWorkedHours(ValidationError):
    code = "invalid_worked_hours"
    default_message = "Отработанные часы — неотрицательное число по участку из списка."
