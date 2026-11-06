from ninja import NinjaAPI
from ninja.testing import TestClient

from src.core.common.api import register_exception_handlers
from src.core.common.exceptions import ConflictError


def test_доменное_исключение_превращается_в_http_ответ() -> None:
    api = NinjaAPI()
    register_exception_handlers(api)

    @api.get("/conflict")
    def raise_conflict(request):  # type: ignore[no-untyped-def]
        raise ConflictError("Заявка уже согласована.")

    client = TestClient(api)
    response = client.get("/conflict")

    assert response.status_code == 409
    assert response.json() == {"code": "conflict", "message": "Заявка уже согласована."}


def test_ошибка_валидации_возвращает_единый_формат() -> None:
    api = NinjaAPI()
    register_exception_handlers(api)

    @api.get("/echo")
    def echo(request, count: int):  # type: ignore[no-untyped-def]
        return {"count": count}

    client = TestClient(api)
    response = client.get("/echo")  # без обязательного query-параметра count

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "errors" in body
