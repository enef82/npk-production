"""Админка модуля «Снабжение и склад».

Справочники (поставщики, типовая оснастка участков) правятся напрямую — побочных
эффектов у них нет; право — снабжение или склад. Строки потребности в админке только
видны: их статусы меняются переходами с проверкой ролей, номером заявки и журналом
заказа — это сервисы, которые вызывает API экрана «Закупки и склад» (CLAUDE.md §5).
Удаление закрыто: на поставщика ссылаются строки (PROTECT), из обращения справочник
выводится флагом «действует».
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.supply.models import PurchaseLine, PurchaseLineHistory, Supplier, ToolTemplate
from src.supply.rules import can_manage_reference


class _ReferenceAdmin(ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(can_manage_reference(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(can_manage_reference(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Supplier)
class SupplierAdmin(_ReferenceAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(ToolTemplate)
class ToolTemplateAdmin(_ReferenceAdmin):
    list_display = ("name", "work_center_id", "category", "quantity", "unit", "price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


class PurchaseLineHistoryInline(TabularInline):
    model = PurchaseLineHistory
    extra = 0
    can_delete = False
    fields = ("created_at", "author", "text")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(PurchaseLine)
class PurchaseLineAdmin(ModelAdmin):
    list_display = (
        "name",
        "requisition_no",
        "status",
        "quantity",
        "unit",
        "need_date",
        "supplier",
        "eta",
    )
    list_filter = ("status", "kind", "category")
    list_select_related = ("supplier",)
    search_fields = ("name", "requisition_no", "po_number")
    inlines = (PurchaseLineHistoryInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
