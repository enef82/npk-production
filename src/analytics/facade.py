"""Публичный интерфейс модуля «Аналитика» для других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8).

Потребитель — команда `seed_demo`: аналитика засевается последней, когда заказы,
табель и контроль уже есть.
"""

from __future__ import annotations

from src.analytics.services import demo as demo_services

__all__ = ["seed_demo"]


def seed_demo() -> None:
    """Закрытые отсечки за 8 прошлых недель (`seedCuts` прототипа)."""

    demo_services.seed_demo()
