"""Админка модуля «Ядро: нумерация»."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from src.core.audit.admin import register_history
from src.core.numbering.models import (  # type: ignore[attr-defined]
    Numerator,
    NumeratorCounter,
    NumeratorEvent,
)


@admin.register(Numerator)
class NumeratorAdmin(ModelAdmin):
    list_display = ("code", "name", "template", "legal_entity", "reset_period", "is_active")
    list_filter = ("reset_period", "is_active", "legal_entity")
    search_fields = ("code", "name", "template")


@admin.register(NumeratorCounter)
class NumeratorCounterAdmin(ModelAdmin):
    """Только чтение — это журнал выдачи, не редактируется руками."""

    list_display = ("numerator", "period_key", "last_value")
    list_filter = ("numerator",)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False


register_history(NumeratorEvent)
