"""Админка модуля «Табель»: справочник кодов вида времени и профили работников —
правка через сервисы (`save_model`, CLAUDE.md §5). Табели подразделений и журнал
только видны: статусы меняются действиями экрана «Табель», где проверяются визы и
блокирующие замечания. Разноска в админке не правится — первичный ввод идёт через
экран, где проверяются открытость периода и лимит дня.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin, TabularInline

from src.core.audit.admin import register_history
from src.timesheet.models import (  # type: ignore[attr-defined]
    TimeCode,
    TimeCodeEvent,
    TimesheetPeriod,
    TimesheetPeriodEvent,
    WorkAllocationEvent,
    WorkerProfile,
    WorkerProfileEvent,
)
from src.timesheet.services.reference import (
    TimeCodeDTO,
    WorkerProfileDTO,
    save_time_code,
    save_worker_profile,
)


def _actor_id(request: HttpRequest) -> UUID:
    return request.user.id  # type: ignore[return-value]


@admin.register(TimeCode)
class TimeCodeAdmin(ModelAdmin):
    list_display = ("code", "name", "is_work", "is_allocatable", "cost_multiplier", "sort_order")
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")

    def has_delete_permission(self, request: HttpRequest, obj: TimeCode | None = None) -> bool:
        # На код ссылается разноска (PROTECT), и он уходит в 1С — код не удаляется.
        return False

    def save_model(self, request: HttpRequest, obj: TimeCode, form: Any, change: bool) -> None:
        saved = save_time_code(
            obj.pk if change else None,
            TimeCodeDTO(
                code=obj.code,
                name=obj.name,
                is_work=obj.is_work,
                is_allocatable=obj.is_allocatable,
                cost_multiplier=obj.cost_multiplier,
                sort_order=obj.sort_order,
            ),
            actor_id=_actor_id(request),
        )
        obj.pk = saved.pk
        obj.created_at = saved.created_at
        obj.updated_at = saved.updated_at


@admin.register(WorkerProfile)
class WorkerProfileAdmin(ModelAdmin):
    list_display = ("employee", "employee_department", "work_center_id", "hourly_rate")
    search_fields = ("employee__full_name", "employee__personnel_number")
    list_select_related = ("employee", "employee__department")
    autocomplete_fields = ("employee",)

    @admin.display(description="Подразделение")
    def employee_department(self, obj: WorkerProfile) -> str:
        return obj.employee.department.name

    def get_readonly_fields(
        self, request: HttpRequest, obj: WorkerProfile | None = None
    ) -> tuple[str, ...]:
        # Профиль — ключ сотрудника: сменить сотрудника у профиля значит завести другой.
        return ("employee",) if obj is not None else ()

    def has_delete_permission(self, request: HttpRequest, obj: WorkerProfile | None = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: WorkerProfile, form: Any, change: bool) -> None:
        saved = save_worker_profile(
            obj.employee_id,
            WorkerProfileDTO(work_center_id=obj.work_center_id, hourly_rate=obj.hourly_rate),
            actor_id=_actor_id(request),
        )
        obj.created_at = saved.created_at
        obj.updated_at = saved.updated_at


class PeriodEventInline(TabularInline):
    model = TimesheetPeriodEvent
    extra = 0
    can_delete = False
    fields = ("created_at", "kind", "version", "actor", "manager", "comment")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(TimesheetPeriod)
class TimesheetPeriodAdmin(ModelAdmin):
    list_display = ("department", "month", "status", "version")
    list_filter = ("status", "month")
    list_select_related = ("department",)
    fields = ("department", "month", "status", "version")
    readonly_fields = fields
    inlines = (PeriodEventInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: TimesheetPeriod | None = None
    ) -> bool:
        return False


for _event_model in (TimeCodeEvent, WorkerProfileEvent, WorkAllocationEvent):
    register_history(_event_model)
