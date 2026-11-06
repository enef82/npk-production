"""Тесты композиционного корня `config/api.py`: автообнаружение роутеров, OpenAPI,
аутентификация, курсорная пагинация. Живут на верхнем уровне (не в src/core/*/tests),
поскольку проверяют собранный API целиком — им по природе нужно видеть модули из
нескольких слоёв ядра сразу, что запрещено `.importlinter` внутри src/core/*."""

from importlib import import_module
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from django.apps import apps
from django.test import Client
from ninja import NinjaAPI, Schema
from ninja.pagination import paginate
from ninja.testing import TestClient

from src.core.identity.models import Party
from src.core.identity.tests.factories import PartyFactory


def test_пакет_без_подпакета_api_вообще_не_ломает_монтирование(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Регрессия на конкретный дефект: до фикса `config/api.py` разбирал только
    `ModuleNotFoundError` от отсутствующего `<module>/api/routers.py`, но не от
    отсутствующего целиком `<module>/api/` — `import_module("<pkg>.api.routers")`,
    когда `<pkg>.api` не существует, поднимает `ModuleNotFoundError` с
    `exc.name == "<pkg>.api"` (родительский пакет), а не с именем `routers.py`, и
    старая проверка `exc.name == module_path` пропускала это дальше как настоящую
    ошибку. `src.core.audit` — стабильный пример «реальный пакет, но без `api/`»."""

    import config.api as config_api

    class _FakeAppConfig:
        name = "src.core.audit"
        label = "core_audit"

    monkeypatch.setattr(
        config_api.apps,  # type: ignore[attr-defined]
        "get_app_configs",
        lambda: [_FakeAppConfig()],
    )

    config_api._mount_routers()  # не должно поднять ModuleNotFoundError


def test_openapi_генерируется_и_валиден() -> None:
    from config.api import api as production_api

    schema = production_api.get_openapi_schema()

    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "НПК Производство API"
    assert schema["paths"]
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            assert operation["responses"], f"{method.upper()} {path} без описанных ответов"


def test_все_роутеры_модулей_подключены_автоматически() -> None:
    from config.api import _router_prefix
    from config.api import api as production_api

    expected_prefixes = set()
    for app_config in apps.get_app_configs():
        if not app_config.name.startswith("src."):
            continue
        try:
            module = import_module(f"{app_config.name}.api.routers")
        except ModuleNotFoundError:
            continue
        if getattr(module, "router", None) is not None:
            expected_prefixes.add(f"/{_router_prefix(app_config.label)}")

    # "" — служебный default_router, который NinjaAPI регистрирует сама себе в
    # конструкторе (docs/openapi.json), не имеет отношения к автообнаружению модулей.
    mounted_prefixes = {prefix for prefix, _ in production_api._routers if prefix != ""}
    assert mounted_prefixes == expected_prefixes
    assert "/documents" in mounted_prefixes  # известный подключённый модуль — не пуст


@pytest.mark.django_db
def test_неаутентифицированный_запрос_отклоняется() -> None:
    client = Client()
    response = client.get(f"/api/v1/documents/{UUID(int=0)}/link")

    assert response.status_code == 401


@pytest.mark.django_db
def test_курсорная_пагинация_не_теряет_и_не_дублирует_записи_при_вставке() -> None:
    """Курсорная (keyset) пагинация из `ninja.pagination.CursorPagination`, настроенная
    как `NINJA_PAGINATION_CLASS` по умолчанию (config/settings/base.py), не должна
    терять и не должна дублировать уже существующие записи, если между запросами
    страниц в таблицу вставляют новую строку — в отличие от offset-пагинации."""

    class PartyIdOut(Schema):
        id: UUID

    api = NinjaAPI()

    @api.get("/parties", response=list[PartyIdOut])
    @paginate
    def list_parties(request):  # type: ignore[no-untyped-def]
        return Party.objects.all()

    initial_ids = {str(PartyFactory().id) for _ in range(5)}  # type: ignore[attr-defined]

    client = TestClient(api)
    collected: list[str] = []
    cursor: str | None = None
    inserted_mid_pagination = False

    for _ in range(10):  # предохранитель от зацикливания при ошибке в курсоре
        path = "/parties?page_size=2" + (f"&cursor={cursor}" if cursor else "")
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        collected += [item["id"] for item in body["results"]]

        if not inserted_mid_pagination:
            PartyFactory()
            inserted_mid_pagination = True

        next_url = body["next"]
        if not next_url:
            break
        cursor = parse_qs(urlsplit(next_url).query)["cursor"][0]

    seen_initial = [item_id for item_id in collected if item_id in initial_ids]
    assert len(seen_initial) == len(initial_ids)
    assert len(seen_initial) == len(set(seen_initial))
