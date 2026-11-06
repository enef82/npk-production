"""Админка модуля «Производство» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1).

Справочники (участки, шаблоны изделий с материалами, операциями и связями, настройки
ответственных) правятся здесь полностью: у них нет сервиса, владеющего переходами.
Заказ, операции, журнал и утверждения документов только видны: этапы с визами, ход
операций и план меняются сервисами через API, где проверяются визы, предшественники и
циклы. Единственное действие над заказом — «Пересчитать план» (сервис `replan_order`).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.apps import apps
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.core.audit.admin import register_history
from src.core.common.exceptions import DomainError
from src.production import rules
from src.production.models import (
    DocumentRelease,
    Operation,
    OrderJournalEntry,
    OrderStageApproval,
    ProductionOrder,
    ProductionSettings,
    ProductTemplate,
    TemplateMaterial,
    TemplateOperation,
    TemplateOperationDependency,
    WorkCenter,
)
from src.production.services.order import replan_order


def _actor_id(request: HttpRequest) -> UUID:
    return request.user.id  # type: ignore[return-value]


class ReferenceAdmin(ModelAdmin):
    """Справочник: правит тот, у кого `production.manage_reference`."""

    def has_module_permission(self, request: HttpRequest) -> bool:
        return super().has_module_permission(request) or bool(
            rules.can_manage_reference(request.user)
        )

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return super().has_view_permission(request, obj) or bool(
            rules.can_manage_reference(request.user)
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(rules.can_manage_reference(request.user))

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(rules.can_manage_reference(request.user))

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(rules.can_manage_reference(request.user))


@admin.register(WorkCenter)
class WorkCenterAdmin(ReferenceAdmin):
    list_display = (
        "short_name",
        "name",
        "phase",
        "hourly_rate",
        "capacity",
        "is_supply",
        "responsible",
        "is_active",
    )
    list_filter = ("phase", "is_supply", "is_active")
    search_fields = ("code", "short_name", "name")
    list_select_related = ("responsible",)
    ordering = ("sort_order", "code")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        # Участок выводится из работы флагом: на него ссылаются операции (PROTECT).
        return False


class TemplateMaterialInline(TabularInline):
    model = TemplateMaterial
    extra = 0
    fields = ("sort_order", "name", "qty_per_unit", "price")


class TemplateOperationInline(TabularInline):
    model = TemplateOperation
    extra = 0
    fields = ("sort_order", "seq", "name", "work_center", "hours", "scales_with_qty", "people")


@admin.register(ProductTemplate)
class ProductTemplateAdmin(ReferenceAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    inlines = (TemplateMaterialInline, TemplateOperationInline)


@admin.register(TemplateOperationDependency)
class TemplateOperationDependencyAdmin(ReferenceAdmin):
    list_display = ("template_code", "predecessor", "successor")
    list_select_related = ("predecessor__template", "successor")
    list_filter = ("predecessor__template",)

    @admin.display(description="Шаблон")
    def template_code(self, obj: TemplateOperationDependency) -> str:
        return obj.predecessor.template.code

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        kwargs["queryset"] = TemplateOperation.objects.select_related("template").order_by(
            "template__code", "seq"
        )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ProductionSettings)
class ProductionSettingsAdmin(ReferenceAdmin):
    list_display = (
        "__str__",
        "launch_responsible",
        "prep_responsible",
        "prod_responsible",
        "qc_responsible",
    )
    list_select_related = (
        "launch_responsible",
        "prep_responsible",
        "prod_responsible",
        "qc_responsible",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and not ProductionSettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ReadOnlyInline(TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class StageApprovalInline(ReadOnlyInline):
    model = OrderStageApproval
    fields = ("stage", "responsible", "approved_by", "approved_at", "comment")
    readonly_fields = fields


class OperationInline(ReadOnlyInline):
    model = Operation
    fields = (
        "seq",
        "name",
        "work_center",
        "hours",
        "people",
        "planned_start",
        "status",
        "progress",
        "responsible",
    )
    readonly_fields = fields
    ordering = ("seq",)


class ReadOnlyAdmin(ModelAdmin):
    """Видно тому, кто ведёт заказы; меняется только сервисами через API."""

    def has_module_permission(self, request: HttpRequest) -> bool:
        return super().has_module_permission(request) or bool(rules.can_manage_orders(request.user))

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return super().has_view_permission(request, obj) or bool(
            rules.can_manage_orders(request.user)
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(ProductionOrder)
class ProductionOrderAdmin(ReadOnlyAdmin):
    list_display = (
        "number",
        "customer_name",
        "product_name",
        "quantity",
        "stage",
        "planned_start",
        "due_date",
        "manager",
    )
    list_filter = ("stage",)
    search_fields = ("number", "inquiry_number", "customer_name", "product_name")
    list_select_related = ("manager",)
    inlines = (StageApprovalInline, OperationInline)
    actions = ["replan_action"]

    @admin.action(description="Пересчитать план")
    def replan_action(self, request: HttpRequest, queryset: QuerySet[ProductionOrder]) -> None:
        if not rules.can_plan_operations(request.user):
            self.message_user(
                request, "Доступно только начальнику производства.", level=messages.ERROR
            )
            return
        employee_id = rules.employee_id_of(request.user)  # type: ignore[arg-type]
        for order in queryset:
            try:
                replan_order(
                    order.pk, None, actor_id=_actor_id(request), actor_employee_id=employee_id
                )
            except DomainError as exc:
                self.message_user(request, f"{order.number}: {exc.message}", level=messages.ERROR)


@admin.register(Operation)
class OperationAdmin(ReadOnlyAdmin):
    list_display = ("order", "seq", "name", "work_center", "status", "progress", "planned_start")
    list_filter = ("status", "work_center")
    search_fields = ("name", "order__number")
    list_select_related = ("order", "work_center")


@admin.register(OrderJournalEntry)
class OrderJournalEntryAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "order", "kind", "author", "text")
    list_filter = ("kind",)
    search_fields = ("order__number", "text")
    list_select_related = ("order", "author")


@admin.register(DocumentRelease)
class DocumentReleaseAdmin(ReadOnlyAdmin):
    list_display = ("document", "order", "operation", "approved_by", "approved_at")
    list_select_related = ("document", "order", "operation", "approved_by")


for _event_model_name in (
    "WorkCenterEvent",
    "ProductTemplateEvent",
    "TemplateMaterialEvent",
    "TemplateOperationEvent",
    "TemplateOperationDependencyEvent",
    "ProductionSettingsEvent",
    "ProductionOrderEvent",
    "OrderStageApprovalEvent",
    "OperationEvent",
    "OperationDependencyEvent",
    "DocumentReleaseEvent",
):
    register_history(apps.get_model("production", _event_model_name))
