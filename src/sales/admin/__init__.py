"""Админка модуля «Заявки и калькуляция» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2).

Справочник причин проигрыша и настройки (экономист, вероятности этапов) правятся здесь —
тем, у кого `sales.manage_calculation` или `production.manage_reference`. Заявки,
калькуляция и визы только видны: этапы, запуск и проигрыш — сервисы через API, где
проверяются визы, калькуляция, план и права менеджера.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.core.audit.admin import register_history
from src.sales.models import (
    CalcMaterial,
    CalcOperation,
    Inquiry,
    InquiryStageApproval,
    LossReason,
    SalesSettings,
)


def _can_manage_reference(request: HttpRequest) -> bool:
    user = request.user
    return bool(
        user.has_perm("sales.manage_calculation") or user.has_perm("production.manage_reference")
    )


class ReferenceAdmin(ModelAdmin):
    def has_module_permission(self, request: HttpRequest) -> bool:
        return super().has_module_permission(request) or _can_manage_reference(request)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return super().has_view_permission(request, obj) or _can_manage_reference(request)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return _can_manage_reference(request)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return _can_manage_reference(request)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Причина выводится из употребления флагом: на неё ссылаются заявки (PROTECT).
        return False


@admin.register(LossReason)
class LossReasonAdmin(ReferenceAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(SalesSettings)
class SalesSettingsAdmin(ReferenceAdmin):
    list_display = ("__str__", "economist", "prob_new", "prob_calc", "prob_approval")
    list_select_related = ("economist",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and not SalesSettings.objects.exists()


class ReadOnlyInline(TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class StageApprovalInline(ReadOnlyInline):
    model = InquiryStageApproval
    fields = ("stage", "responsible", "approved_by", "approved_at", "comment")
    readonly_fields = fields


class MaterialInline(ReadOnlyInline):
    model = CalcMaterial
    fields = ("name", "quantity", "price")
    readonly_fields = fields


class OperationInline(ReadOnlyInline):
    model = CalcOperation
    fields = ("seq", "name", "work_center_id", "hours", "people", "planned_start")
    readonly_fields = fields
    ordering = ("seq",)


@admin.register(Inquiry)
class InquiryAdmin(ModelAdmin):
    list_display = (
        "number",
        "customer_name",
        "product_name",
        "quantity",
        "stage",
        "due_date",
        "manager",
    )
    list_filter = ("stage",)
    search_fields = ("number", "customer_name", "object_name", "product_name")
    list_select_related = ("manager",)
    inlines = (StageApprovalInline, MaterialInline, OperationInline)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for _event_model_name in (
    "LossReasonEvent",
    "SalesSettingsEvent",
    "InquiryEvent",
    "InquiryStageApprovalEvent",
    "CalcMaterialEvent",
    "CalcOperationEvent",
    "CalcOperationDependencyEvent",
):
    register_history(apps.get_model("sales", _event_model_name))
