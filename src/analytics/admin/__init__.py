"""Админка модуля «Аналитика».

Отсечки и их журнал — только чтение: закрытие снимает живые данные нескольких модулей,
переоткрытие требует причины и пишет журнал — это сервис, который вызывает экран
«Отсечки» (CLAUDE.md §5). Строки снимка к тому же защищены от правки триггером БД.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.analytics.models import WeeklyCutoff, WeeklyCutoffEvent, WeeklyCutoffRow


class _ReadOnlyMixin:
    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class WeeklyCutoffRowInline(_ReadOnlyMixin, TabularInline):
    model = WeeklyCutoffRow
    extra = 0
    fields = (
        "work_center_id",
        "planned_hours",
        "earned_hours",
        "worked_hours",
        "checked",
        "defects",
    )
    readonly_fields = fields


@admin.register(WeeklyCutoff)
class WeeklyCutoffAdmin(_ReadOnlyMixin, ModelAdmin):
    list_display = ("week_start", "closed_by", "closed_at", "comment")
    list_select_related = ("closed_by",)
    date_hierarchy = "week_start"
    inlines = (WeeklyCutoffRowInline,)


@admin.register(WeeklyCutoffEvent)
class WeeklyCutoffEventAdmin(_ReadOnlyMixin, ModelAdmin):
    list_display = ("week_start", "action", "actor", "created_at", "text")
    list_filter = ("action",)
    list_select_related = ("actor",)
