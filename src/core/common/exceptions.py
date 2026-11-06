from typing import Any


class DomainError(Exception):
    """Базовое доменное исключение. Наследники — единственный способ сообщить об ошибке домена.

    `details` — необязательная структурированная нагрузка; её форма определяется
    конкретным `code` (например, у `DuplicatesFound` это список кандидатов в дубликаты).
    Большинство ошибок `details` не несут, поле остаётся `None`, и в ответ API не попадает.
    """

    code = "domain_error"
    status_code = 400
    default_message = "Ошибка домена."

    def __init__(self, message: str | None = None, *, details: Any | None = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class ValidationError(DomainError):
    code = "validation_error"
    status_code = 400
    default_message = "Данные не прошли проверку."


class PermissionDenied(DomainError):
    code = "permission_denied"
    status_code = 403
    default_message = "Недостаточно прав для выполнения действия."


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409
    default_message = "Конфликт состояния: операция невозможна."


class ServiceUnavailableError(DomainError):
    """Отказ внешнего сервиса, от которого зависит операция (Gotenberg, 1С, LLM).

    Отдельный статус (503), а не 409: причина не в состоянии агрегата, а в
    недоступности зависимости, и клиенту осмысленно повторить тот же запрос позже.
    Обработчики API отдают её как 503, а не как 500 — «внятная ошибка, а не пятисотка».
    """

    code = "service_unavailable"
    status_code = 503
    default_message = "Внешний сервис временно недоступен. Повторите позже."
