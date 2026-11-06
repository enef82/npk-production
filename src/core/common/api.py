from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError

from src.core.common.exceptions import DomainError

# Конвенция именования Pydantic-схем модулей (`api/schemas.py`), переиспользуемая
# через core, где нужно (см. src.core.documents.api.schemas.DocumentOut):
#   XxxIn        — тело запроса на создание/изменение
#   XxxOut       — полное представление сущности в ответе
#   XxxListItem  — облегчённая проекция сущности в списочном ответе (без тяжёлых
#                  полей XxxOut, чтобы список не тянул лишнее на каждую строку)


def register_exception_handlers(api: NinjaAPI) -> None:
    """Приводит формат ответа об ошибке к единому виду {"code", "message"} для всех
    веток, где django-ninja по умолчанию отдаёт свой формат ({"detail": ...})."""

    @api.exception_handler(DomainError)
    def handle_domain_error(request: HttpRequest, exc: DomainError) -> HttpResponse:
        payload: dict[str, object] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            payload["details"] = exc.details
        return api.create_response(request, payload, status=exc.status_code)

    @api.exception_handler(NinjaValidationError)
    def handle_validation_error(request: HttpRequest, exc: NinjaValidationError) -> HttpResponse:
        return api.create_response(
            request,
            {
                "code": "validation_error",
                "message": "Данные не прошли проверку.",
                "errors": exc.errors,
            },
            status=422,
        )

    @api.exception_handler(HttpError)
    def handle_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        return api.create_response(
            request,
            {"code": "http_error", "message": str(exc)},
            status=exc.status_code,
        )

    @api.exception_handler(Http404)
    def handle_not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
        return api.create_response(
            request,
            {"code": "not_found", "message": "Не найдено."},
            status=404,
        )
