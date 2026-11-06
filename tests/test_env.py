import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

import config.settings.base as base_settings
from config.settings.env import build_database_config


def test_database_url_разбирается_в_настройки() -> None:
    config = build_database_config("psql://npk_prod:npk_prod@localhost:55432/npk_prod")

    assert config["ENGINE"] == "django.db.backends.postgresql"
    assert config["NAME"] == "npk_prod"
    assert config["USER"] == "npk_prod"
    assert config["PASSWORD"] == "npk_prod"
    assert config["HOST"] == "localhost"
    assert config["PORT"] == 55432


def test_отсутствие_secret_key_валит_запуск(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ImproperlyConfigured):
        importlib.reload(base_settings)


def test_production_allowed_hosts_точный_состав(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Полный список того, кто обращается к `web` и под каким Host — не "содержит",
    # а точный состав (docs/checklist-prod-perehod.md, К2): следующая правка
    # настроек не должна молча выкинуть одно из внутренних имён. Два внутренних
    # docker-вызова обращаются к `web` не по публичному имени — healthcheck
    # контейнера `web` (http://localhost:8000/healthz) и серверная проверка
    # сессии в `frontend` (lib/auth/session.ts, BACKEND_ORIGIN, http://web:8000/).
    # Caddy в обоих не участвует и не может подставить публичное имя. Оба дефекта
    # воспроизвелись на бою 2026-09-18 (второй — как «страница входа виснет»:
    # вход на бэкенде проходил, но серверная проверка сессии после него молча
    # проваливалась). Celery/cron/скрипты пока не обращаются к web по HTTP — если
    # появятся, добавить сюда и в config/settings/production.py одновременно.
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ALLOWED_HOSTS", "ee3.kt96.ru")
    try:
        importlib.reload(base_settings)
        import config.settings.production as production_settings

        importlib.reload(production_settings)

        assert set(production_settings.ALLOWED_HOSTS) == {"ee3.kt96.ru", "localhost", "web"}
    finally:
        monkeypatch.undo()
        importlib.reload(base_settings)
