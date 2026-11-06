"""Загрузка и разбор переменных окружения для настроек Django."""

from pathlib import Path
from typing import Any, cast

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(str(BASE_DIR / ".env"))


def build_database_config(url: str) -> dict[str, Any]:
    """Разбирает DATABASE_URL в словарь настроек DATABASES."""
    return cast(dict[str, Any], environ.Env.db_url_config(url))
