"""Админка модуля «Ядро: организационная структура»."""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from src.core.audit.admin import register_history
from src.core.org.models import (  # type: ignore[attr-defined]
    CostCenter,
    CostCenterEvent,
    Department,
    DepartmentEvent,
    Employee,
    EmployeeEvent,
    LegalEntity,
    LegalEntityEvent,
    Position,
    PositionEvent,
)
from src.core.org.services import set_primary_legal_entity


@admin.register(LegalEntity)
class LegalEntityAdmin(ModelAdmin):
    list_display = ("print_name", "tax_system", "is_primary", "default_signatory")
    list_filter = ("tax_system", "is_primary")
    search_fields = ("print_name",)
    readonly_fields = ("is_primary",)
    actions = ["make_primary"]
    list_select_related = ("default_signatory",)

    @admin.action(description="Сделать основной организацией")
    def make_primary(self, request: HttpRequest, queryset: QuerySet[LegalEntity]) -> None:
        legal_entity = queryset.first()
        if legal_entity is not None:
            set_primary_legal_entity(legal_entity.pk)


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ("name", "code", "parent", "head", "legal_entity")
    list_filter = ("legal_entity",)
    search_fields = ("name", "code")


@admin.register(CostCenter)
class CostCenterAdmin(ModelAdmin):
    list_display = ("name", "code", "department")
    search_fields = ("name", "code")


@admin.register(Position)
class PositionAdmin(ModelAdmin):
    list_display = ("name", "category", "grade")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin):
    list_display = ("full_name", "personnel_number", "department", "position", "status")
    list_filter = ("status", "department", "position__category")
    search_fields = ("full_name", "personnel_number")
    list_select_related = ("department", "position")


for _event_model in (
    LegalEntityEvent,
    DepartmentEvent,
    CostCenterEvent,
    PositionEvent,
    EmployeeEvent,
):
    register_history(_event_model)
