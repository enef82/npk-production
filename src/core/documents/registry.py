"""Реестр видимости сущностей, заполняемый через `AppConfig.ready()` — тот же приём,
что `core.identity.registry` для профилей (И1: ядру запрещено импортировать
функциональные модули).

`can_download` (`rules.py`) не может спросить «видит ли пользователь эту заявку» —
это знает только `crm`. Вызывающий модуль регистрирует свою проверку сам:

    # src/crm/apps.py
    class CrmConfig(AppConfig):
        def ready(self) -> None:
            from src.core.documents.registry import register_entity_visibility_checker
            from .rules import can_view_inquiry
            register_entity_visibility_checker("crm.inquiry", _check_inquiry_visibility)

До исправления 18.09 здесь проверялось «документ привязан хоть к чему-то» — это
воспроизводило дыру presigned-URL (не перепроверялся вовсе), а не право: любой
аутентифицированный читал чужие КП. Решение 1 ADR 0029 платит воркером на каждое
скачивание именно ради настоящей проверки, не ради «вошёл в систему»."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from src.core.accounts.models import User

EntityVisibilityChecker = Callable[[User, UUID], bool]

_checkers: dict[str, EntityVisibilityChecker] = {}


def register_entity_visibility_checker(entity_type: str, checker: EntityVisibilityChecker) -> None:
    _checkers[entity_type] = checker


def can_view_entity(user: User, entity_type: str, entity_id: UUID) -> bool:
    """`False`, если для `entity_type` никто не зарегистрировался — не молчаливое
    разрешение. Документ, привязанный к сущности без зарегистрированной проверки,
    доступен только загрузившему и администратору (`can_download`)."""

    checker = _checkers.get(entity_type)
    if checker is None:
        return False
    return checker(user, entity_id)
