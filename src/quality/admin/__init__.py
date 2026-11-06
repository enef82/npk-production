"""Админка модуля «ОТК и качество».

Справочники (точки контроля, виды дефектов, причины) правятся напрямую — побочных
эффектов у них нет; право — `quality.manage_reference`. Записи контроля в админке
только видны: запись пишет журнал заказа в той же транзакции и проверяет этап заказа и
точку контроля — это сервис, который вызывает API карточки операции (CLAUDE.md §5).
Удаление закрыто: на справочники ссылаются записи (PROTECT), из обращения справочник
выводится флагом «действует».
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord
from src.quality.rules import can_manage_reference


class _ReferenceAdmin(ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(can_manage_reference(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_reference(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class DefectTypeInline(TabularInline):
    model = DefectType
    extra = 0
    can_delete = False
    fields = ("name", "order", "is_active")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_reference(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_reference(request.user))


@admin.register(InspectionPoint)
class InspectionPointAdmin(_ReferenceAdmin):
    list_display = ("name", "work_center_id", "is_final", "is_active")
    list_filter = ("is_final", "is_active")
    search_fields = ("name",)
    inlines = (DefectTypeInline,)


@admin.register(DefectType)
class DefectTypeAdmin(_ReferenceAdmin):
    list_display = ("name", "inspection_point", "order", "is_active")
    list_filter = ("is_active", "inspection_point")
    list_select_related = ("inspection_point",)
    search_fields = ("name",)


@admin.register(DefectCause)
class DefectCauseAdmin(_ReferenceAdmin):
    list_display = ("name", "is_operator_fault", "order", "is_active")
    list_filter = ("is_active",)


@admin.register(InspectionRecord)
class InspectionRecordAdmin(ModelAdmin):
    list_display = ("date", "work_center_id", "inspector", "checked", "rework", "scrap", "cause")
    list_filter = ("cause",)
    list_select_related = ("inspector", "cause", "defect_type")
    date_hierarchy = "date"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
