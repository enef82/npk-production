"""Единая точка входа django-ninja. Монтируется в config/urls.py под /api/v1/.

Роутеры подключаются автообнаружением по соглашению `<module>/api/routers.py` →
атрибут `router`, а не явным перечислением — это композиционный корень, ему знать
про все модули можно (в отличие от прикладного кода, которому запрещено импортировать
чужие модули мимо facade.py, И1). Модули без `api/routers.py` или без атрибута
`router` в нём — не подключаются, ошибки не возникает: у большинства модулей ядра
и всех восьми функциональных блоков api/ пока заглушка, эндпоинты появятся тогда,
когда появится потребитель.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps
from ninja import NinjaAPI
from ninja.security import django_auth
from ninja.throttling import AnonRateThrottle, AuthRateThrottle

from src.core.common.api import register_exception_handlers

api = NinjaAPI(
    title="НПК Производство API",
    version="1.0.0",
    auth=django_auth,
    throttle=[AuthRateThrottle(), AnonRateThrottle()],
)
register_exception_handlers(api)


def _router_prefix(label: str) -> str:
    """`core_documents` → `documents`, `crm` → `crm`."""

    return label.removeprefix("core_")


def _mount_routers() -> None:
    for app_config in sorted(apps.get_app_configs(), key=lambda c: c.label):
        if not app_config.name.startswith("src."):
            continue
        module_path = f"{app_config.name}.api.routers"
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as exc:
            # Различаем «этого модуля нет» (заглушка или пакет вообще без api/ —
            # пакет без `api/` вовсе — пропускаем) и «модуль
            # есть, но у него самого битый импорт» (реальная ошибка, не глотаем её) —
            # во втором случае exc.name
            # указывает на чужой отсутствующий модуль, а не на сам routers.py/api.
            if exc.name in {module_path, f"{app_config.name}.api"}:
                continue
            raise
        router = getattr(module, "router", None)
        if router is None:
            continue
        api.add_router(f"/{_router_prefix(app_config.label)}", router)


_mount_routers()
