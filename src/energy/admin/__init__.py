"""Админка модуля «Энергоучёт».

Тарифы и счётчики — через сервисы (`save_model`): тариф ресурса пересчитывается
по периодам, дерево счётчиков проверяется на цикл. Интервалы, показания и пакеты
SCADA только видны: показание раскладывает расход по интервалам — его вносят через
API экрана «Энергоучёт», интервалы приходят из SCADA (CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from src.energy.models import (
    EnergyResource,
    Meter,
    MeterInterval,
    MeterReading,
    ScadaMessage,
    TariffPeriod,
)
from src.energy.rules import can_manage_meters
from src.energy.services.meter import MeterDTO, create_meter, update_meter
from src.energy.services.resource import set_tariff


def _actor_id(request: HttpRequest) -> UUID:
    return request.user.id  # type: ignore[return-value]


class _ReadOnlyAdmin(ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(EnergyResource)
class EnergyResourceAdmin(_ReadOnlyAdmin):
    """Состав ресурсов задан миграцией; тариф меняется периодом тарифа."""

    list_display = ("code", "name", "unit", "tariff")


@admin.register(TariffPeriod)
class TariffPeriodAdmin(ModelAdmin):
    list_display = ("resource", "valid_from", "tariff")
    list_select_related = ("resource",)
    list_filter = ("resource",)
    fields = ("resource", "valid_from", "tariff")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(can_manage_meters(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_meters(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        return ("resource", "valid_from") if obj is not None else ()

    def save_model(self, request: HttpRequest, obj: TariffPeriod, form: Any, change: bool) -> None:
        set_tariff(obj.resource_id, obj.valid_from, obj.tariff, actor_id=_actor_id(request))
        saved = TariffPeriod.objects.get(resource_id=obj.resource_id, valid_from=obj.valid_from)
        obj.pk = saved.pk
        obj.created_at = saved.created_at
        obj.updated_at = saved.updated_at


@admin.register(Meter)
class MeterAdmin(ModelAdmin):
    list_display = ("code", "name", "resource", "parent", "kind", "source")
    list_filter = ("resource", "kind", "source")
    list_select_related = ("resource", "parent")
    search_fields = ("code", "name")
    fields = ("code", "name", "resource", "parent", "kind", "equipment_id", "source", "order")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(can_manage_meters(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_meters(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Meter, form: Any, change: bool) -> None:
        dto = MeterDTO(
            code=obj.code,
            name=obj.name,
            resource_id=obj.resource_id,
            kind=obj.kind,  # type: ignore[arg-type]
            parent_id=obj.parent_id,
            equipment_id=obj.equipment_id,
            source=obj.source,  # type: ignore[arg-type]
            order=obj.order,
        )
        if change:
            update_meter(obj.pk, dto, actor_id=_actor_id(request))
            return
        created = create_meter(dto, actor_id=_actor_id(request))
        obj.pk = created.pk
        obj.created_at = created.created_at
        obj.updated_at = created.updated_at


@admin.register(MeterInterval)
class MeterIntervalAdmin(_ReadOnlyAdmin):
    list_display = ("meter", "start", "value", "source")
    list_select_related = ("meter",)
    list_filter = ("source",)
    date_hierarchy = "start"
    show_full_result_count = False


@admin.register(MeterReading)
class MeterReadingAdmin(_ReadOnlyAdmin):
    list_display = ("meter", "taken_at", "value")
    list_select_related = ("meter",)


@admin.register(ScadaMessage)
class ScadaMessageAdmin(_ReadOnlyAdmin):
    list_display = ("message_id", "source_id", "items_accepted", "items_rejected", "created_at")
    search_fields = ("message_id",)
