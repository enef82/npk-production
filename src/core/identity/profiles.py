"""Абстрактные базы профилей модулей поверх ядра идентичности.

Модуль строит профиль над `Party` или `Item`, наследуя `PartyProfile`/`ItemProfile`.
Профиль хранит модульные атрибуты в `attributes` (JSONB), которые по желанию модуля
валидируются по `AttributeSchema`, зарегистрированной под парой (app_label, category)
через `core.identity.services.attributes.validate_against_schema`.

`clean()` — вторичная защита для админки и `ModelForm` (Django вызывает `clean()`
только через них, не через обычный `save()`). Основной путь валидации — сервис
`core.identity.services.profiles.update_profile_attributes`, единственная точка,
где `attributes` реально меняются (инвариант И3).
"""

from __future__ import annotations

from django.db import models

from src.core.identity.services.attributes import validate_against_schema


class PartyProfile(models.Model):
    party = models.OneToOneField(
        "core_identity.Party",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="%(app_label)s_profile",
        verbose_name="Контрагент",
    )
    attributes = models.JSONField("Атрибуты", default=dict, blank=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        abstract = True

    @property
    def app_label(self) -> str:
        return self._meta.app_label

    @property
    def category(self) -> str:
        return self._meta.model_name  # type: ignore[return-value]

    def clean(self) -> None:
        validate_against_schema(self.attributes, self.app_label, self.category)


class ItemProfile(models.Model):
    item = models.OneToOneField(
        "core_identity.Item",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="%(app_label)s_profile",
        verbose_name="Номенклатура",
    )
    attributes = models.JSONField("Атрибуты", default=dict, blank=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        abstract = True

    @property
    def app_label(self) -> str:
        return self._meta.app_label

    @property
    def category(self) -> str:
        return self._meta.model_name  # type: ignore[return-value]

    def clean(self) -> None:
        validate_against_schema(self.attributes, self.app_label, self.category)
