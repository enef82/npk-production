"""Ленивое создание и правка профилей модулей поверх ядра идентичности.

`update_profile_attributes` — единственная точка, где `attributes` профиля
реально меняются, и поэтому единственное место, где валидация по JSON Schema
гарантированно происходит (инвариант И3). `PartyProfile.clean()`/`ItemProfile.clean()`
дублируют ту же проверку только для админки и `ModelForm` — Django не вызывает
`clean()` при обычном `save()`, так что полагаться на него в сервисном коде нельзя.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.core.identity.profiles import ItemProfile, PartyProfile
from src.core.identity.services.attributes import validate_against_schema


def _entity_field[M: PartyProfile | ItemProfile](profile_model: type[M]) -> str:
    if issubclass(profile_model, PartyProfile):
        return "party_id"
    if issubclass(profile_model, ItemProfile):
        return "item_id"
    raise TypeError(f"{profile_model!r} не наследует PartyProfile или ItemProfile")


def get_or_create_profile[M: PartyProfile | ItemProfile](
    profile_model: type[M], entity_id: UUID, *, actor_id: UUID
) -> M:
    with transaction.atomic(), actor_context(actor_id):
        profile, _ = profile_model.objects.get_or_create(  # type: ignore[attr-defined]
            **{_entity_field(profile_model): entity_id}
        )
    return cast(M, profile)


def update_profile_attributes[M: PartyProfile | ItemProfile](
    profile_model: type[M], entity_id: UUID, attributes: dict[str, Any], *, actor_id: UUID
) -> M:
    with transaction.atomic(), actor_context(actor_id):
        profile = get_or_create_profile(profile_model, entity_id, actor_id=actor_id)
        validate_against_schema(attributes, profile.app_label, profile.category)
        profile.attributes = attributes
        profile.save(update_fields=["attributes"])
    return profile
