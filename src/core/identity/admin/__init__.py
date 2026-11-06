"""Админка модуля «Ядро: идентичность»."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django import forms
from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from src.core.audit.admin import register_history
from src.core.identity.models import (  # type: ignore[attr-defined]
    AttributeSchema,
    AttributeSchemaEvent,
    Item,
    ItemEvent,
    ItemType,
    Party,
    PartyEvent,
    PartyType,
    UnitOfMeasure,
    UnitOfMeasureEvent,
)
from src.core.identity.services.dedup import find_item_duplicates, find_party_duplicates
from src.core.identity.services.item import ItemCreateDTO, ItemUpdateDTO, create_item, update_item
from src.core.identity.services.party import (
    PartyCreateDTO,
    PartyUpdateDTO,
    create_party,
    update_party,
)


def _duplicates_message(matches: list[Any]) -> str:
    candidates = "; ".join(f"«{m.candidate}» ({m.reason}, совпадение {m.score})" for m in matches)
    return (
        f"Найдены вероятные дубликаты: {candidates}. Если это не дубликат — отметьте "
        "«Создать несмотря на дубликаты» и сохраните ещё раз."
    )


def _actor_id(request: HttpRequest) -> UUID:
    """`request.user` в статической типизации допускает `AnonymousUser` (`.id is None`),
    но в save_model админки пользователь уже аутентифицирован (иначе не дошёл бы сюда)."""
    return request.user.id  # type: ignore[return-value]


class PartyAdminForm(forms.ModelForm):  # type: ignore[type-arg]
    force_create = forms.BooleanField(required=False, label="Создать несмотря на дубликаты")

    class Meta:
        model = Party
        fields = ("inn", "kpp", "legal_name", "short_name", "party_type")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        # UUIDPrimaryKeyModel заполняет `id` через default=uuid7 сразу при
        # конструировании объекта — self.instance.pk истинен даже для новой,
        # ещё не сохранённой записи. Настоящий признак «это добавление» —
        # `_state.adding`, а не наличие pk.
        if not self.instance._state.adding or cleaned.get("force_create"):
            return cleaned
        matches = find_party_duplicates(
            inn=cleaned.get("inn", ""),
            kpp=cleaned.get("kpp", ""),
            name=cleaned.get("short_name", ""),
        )
        if matches:
            raise forms.ValidationError(_duplicates_message(matches))
        return cleaned


class ItemAdminForm(forms.ModelForm):  # type: ignore[type-arg]
    force_create = forms.BooleanField(required=False, label="Создать несмотря на дубликаты")

    class Meta:
        model = Item
        fields = ("code", "name", "item_type", "base_uom")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if not self.instance._state.adding or cleaned.get("force_create"):
            return cleaned
        matches = find_item_duplicates(code=cleaned.get("code", ""), name=cleaned.get("name", ""))
        if matches:
            raise forms.ValidationError(_duplicates_message(matches))
        return cleaned


@admin.register(Party)
class PartyAdmin(ModelAdmin):
    """Создание и изменение идут через `create_party`/`update_party` (И5, И3) —
    прямой `Party.objects.create()`/`obj.save()` в обход сервиса запрещён."""

    form = PartyAdminForm
    list_display = ("short_name", "legal_name", "inn", "kpp", "party_type", "status")
    list_filter = ("party_type", "status")
    search_fields = ("short_name", "legal_name", "inn", "kpp")

    def get_readonly_fields(
        self, request: HttpRequest, obj: Party | None = None
    ) -> tuple[str, ...]:
        return ("inn", "kpp") if obj is not None else ()

    def save_model(
        self, request: HttpRequest, obj: Party, form: PartyAdminForm, change: bool
    ) -> None:
        if change:
            updated = update_party(
                obj.pk,
                PartyUpdateDTO(
                    legal_name=obj.legal_name,
                    short_name=obj.short_name,
                    party_type=PartyType(obj.party_type),
                ),
                actor_id=_actor_id(request),
            )
        else:
            updated = create_party(
                PartyCreateDTO(
                    inn=obj.inn,
                    kpp=obj.kpp,
                    legal_name=obj.legal_name,
                    short_name=obj.short_name,
                    party_type=PartyType(obj.party_type),
                ),
                actor_id=_actor_id(request),
                force=form.cleaned_data.get("force_create", False),
            )
        obj.pk = updated.pk
        obj.status = updated.status
        obj.created_at = updated.created_at
        obj.updated_at = updated.updated_at


@admin.register(Item)
class ItemAdmin(ModelAdmin):
    """Создание и изменение идут через `create_item`/`update_item` (И5, И3)."""

    form = ItemAdminForm
    list_display = ("code", "name", "item_type", "base_uom", "status")
    list_filter = ("item_type", "status")
    search_fields = ("code", "name")
    list_select_related = ("base_uom",)

    def get_readonly_fields(self, request: HttpRequest, obj: Item | None = None) -> tuple[str, ...]:
        return ("code",) if obj is not None else ()

    def save_model(
        self, request: HttpRequest, obj: Item, form: ItemAdminForm, change: bool
    ) -> None:
        if change:
            updated = update_item(
                obj.pk,
                ItemUpdateDTO(
                    name=obj.name,
                    item_type=ItemType(obj.item_type),
                    base_uom_id=obj.base_uom_id,
                ),
                actor_id=_actor_id(request),
            )
        else:
            updated = create_item(
                ItemCreateDTO(
                    code=obj.code,
                    name=obj.name,
                    item_type=ItemType(obj.item_type),
                    base_uom_id=obj.base_uom_id,
                ),
                actor_id=_actor_id(request),
                force=form.cleaned_data.get("force_create", False),
            )
        obj.pk = updated.pk
        obj.status = updated.status
        obj.created_at = updated.created_at
        obj.updated_at = updated.updated_at


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(ModelAdmin):
    list_display = ("code", "name", "okei_code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AttributeSchema)
class AttributeSchemaAdmin(ModelAdmin):
    list_display = ("app_label", "category", "is_active")
    list_filter = ("app_label", "is_active")
    search_fields = ("app_label", "category")


for _event_model in (PartyEvent, ItemEvent, UnitOfMeasureEvent, AttributeSchemaEvent):
    register_history(_event_model)
