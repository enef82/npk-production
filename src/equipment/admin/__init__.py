"""Админка модуля «Оборудование и ТО».

Справочники причин и категорий правятся напрямую — побочных эффектов у них нет.
Оборудование и виды ТО — через сервисы (`save_model`); состояние оборудования только
для чтения, меняется действием. Наработка, ремонты и проведённые ТО в админке только
видны: их правила (24 ч в сутки, закрытие с событием в табель) — в сервисах, которые
вызывает API экрана «Оборудование» (CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.core.common.exceptions import DomainError
from src.equipment.models import (
    DownReason,
    Equipment,
    EquipmentStatus,
    FailureCategory,
    IdleReason,
    MaintenanceRecord,
    MaintenanceType,
    Repair,
    RepairWorker,
    RuntimeLog,
)
from src.equipment.rules import can_manage_equipment
from src.equipment.services.equipment import (
    EquipmentDTO,
    MaintenanceTypeDTO,
    create_equipment,
    create_maintenance_type,
    set_equipment_status,
    update_equipment,
    update_maintenance_type,
)


def _actor_id(request: HttpRequest) -> UUID:
    return request.user.id  # type: ignore[return-value]


class _ManagedAdmin(ModelAdmin):
    """Правка — по праву `equipment.manage_equipment`; удаление закрыто: на записи
    ссылаются журналы (PROTECT), справочник выводится из обращения флагом."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(can_manage_equipment(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_equipment(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class _ReadOnlyAdmin(ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(IdleReason)
class IdleReasonAdmin(_ManagedAdmin):
    list_display = ("name", "order", "is_active")
    list_filter = ("is_active",)


@admin.register(DownReason)
class DownReasonAdmin(_ManagedAdmin):
    list_display = ("name", "repair_kind", "order", "is_active")
    list_filter = ("is_active",)


@admin.register(FailureCategory)
class FailureCategoryAdmin(_ManagedAdmin):
    list_display = ("name", "order", "is_active")
    list_filter = ("is_active",)


class MaintenanceTypeInline(TabularInline):
    model = MaintenanceType
    extra = 0
    can_delete = False
    fields = ("code", "interval_hours", "scope")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Equipment)
class EquipmentAdmin(_ManagedAdmin):
    list_display = ("inventory_no", "name", "control_system", "status")
    list_filter = ("status",)
    search_fields = ("inventory_no", "name")
    fields = (
        "inventory_no",
        "name",
        "work_center_id",
        "control_system",
        "connection",
        "operating_hours_initial",
        "status",
    )
    readonly_fields = ("status",)
    inlines = (MaintenanceTypeInline,)
    actions = ["mark_run", "mark_idle"]

    def save_model(self, request: HttpRequest, obj: Equipment, form: Any, change: bool) -> None:
        dto = EquipmentDTO(
            inventory_no=obj.inventory_no,
            name=obj.name,
            work_center_id=obj.work_center_id,
            control_system=obj.control_system,
            connection=obj.connection,
            operating_hours_initial=obj.operating_hours_initial,
        )
        if change:
            update_equipment(obj.pk, dto, actor_id=_actor_id(request))
            return
        created = create_equipment(dto, actor_id=_actor_id(request))
        obj.pk = created.pk
        obj.created_at = created.created_at
        obj.updated_at = created.updated_at

    def _set_status(
        self, request: HttpRequest, queryset: QuerySet[Equipment], status: EquipmentStatus
    ) -> None:
        for equipment in queryset:
            try:
                set_equipment_status(equipment.id, status, actor_id=_actor_id(request))
            except DomainError as exc:
                self.message_user(request, f"{equipment}: {exc.message}", messages.ERROR)

    @admin.action(description="Состояние: работает")
    def mark_run(self, request: HttpRequest, queryset: QuerySet[Equipment]) -> None:
        self._set_status(request, queryset, EquipmentStatus.RUN)

    @admin.action(description="Состояние: простаивает")
    def mark_idle(self, request: HttpRequest, queryset: QuerySet[Equipment]) -> None:
        self._set_status(request, queryset, EquipmentStatus.IDLE)


@admin.register(MaintenanceType)
class MaintenanceTypeAdmin(_ManagedAdmin):
    list_display = ("equipment", "code", "interval_hours")
    list_select_related = ("equipment",)
    search_fields = ("code", "equipment__name", "equipment__inventory_no")
    fields = ("equipment", "code", "interval_hours", "scope")

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        return ("equipment",) if obj is not None else ()

    def save_model(
        self, request: HttpRequest, obj: MaintenanceType, form: Any, change: bool
    ) -> None:
        dto = MaintenanceTypeDTO(code=obj.code, interval_hours=obj.interval_hours, scope=obj.scope)
        if change:
            update_maintenance_type(obj.pk, dto, actor_id=_actor_id(request))
            return
        created = create_maintenance_type(obj.equipment_id, dto, actor_id=_actor_id(request))
        obj.pk = created.pk
        obj.created_at = created.created_at
        obj.updated_at = created.updated_at


@admin.register(RuntimeLog)
class RuntimeLogAdmin(_ReadOnlyAdmin):
    list_display = ("equipment", "date", "run", "setup", "idle", "down", "source")
    list_filter = ("source",)
    list_select_related = ("equipment",)
    date_hierarchy = "date"


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(_ReadOnlyAdmin):
    list_display = ("maintenance_type", "date", "at_hours", "performed_by")
    list_select_related = ("maintenance_type", "performed_by")


class RepairWorkerInline(TabularInline):
    model = RepairWorker
    extra = 0
    can_delete = False
    fields = ("employee", "hours")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Repair)
class RepairAdmin(_ReadOnlyAdmin):
    list_display = ("number", "equipment", "kind", "started_at", "finished_at", "status")
    list_filter = ("kind", "status")
    list_select_related = ("equipment",)
    search_fields = ("number", "equipment__name", "description")
    inlines = (RepairWorkerInline,)
