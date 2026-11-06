from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.apps import AppConfig

if TYPE_CHECKING:
    from src.core.accounts.models import User


def _any_authenticated(user: User, entity_id: UUID) -> bool:
    # Чтение всех экранов производства — любой аутентифицированный
    # (`docs/spec/00-prilozhenie-proizvodstvo.md` §4): документы заказа тоже.
    return bool(user.is_authenticated)


class ProductionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.production"
    verbose_name = "Производство"

    def ready(self) -> None:
        from src.core.documents.registry import register_entity_visibility_checker

        register_entity_visibility_checker("production.order", _any_authenticated)
        register_entity_visibility_checker("production.operation", _any_authenticated)
