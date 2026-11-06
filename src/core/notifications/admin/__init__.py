"""Админка модуля «Ядро: уведомления»."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from src.core.audit.admin import register_history
from src.core.notifications.models import (  # type: ignore[attr-defined]
    Notification,
    NotificationDigest,
    NotificationTemplate,
    NotificationTemplateEvent,
    UserNotificationSetting,
    UserNotificationSettingEvent,
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(ModelAdmin):
    list_display = ("code", "channel")
    list_filter = ("channel",)
    search_fields = ("code",)


@admin.register(UserNotificationSetting)
class UserNotificationSettingAdmin(ModelAdmin):
    list_display = ("user", "code", "channel", "is_enabled", "delivery_mode")
    list_filter = ("channel", "delivery_mode", "is_enabled")
    search_fields = ("user__email", "code")
    list_select_related = ("user",)


class _ReadOnlyLogAdmin(ModelAdmin):
    """Общий предок для логов доставки — не редактируются руками."""

    list_select_related = ("user",)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False


@admin.register(Notification)
class NotificationAdmin(_ReadOnlyLogAdmin):
    list_display = ("user", "code", "channel", "delivery_mode", "status", "created_at")
    list_filter = ("channel", "delivery_mode", "status")
    search_fields = ("user__email", "code")


@admin.register(NotificationDigest)
class NotificationDigestAdmin(_ReadOnlyLogAdmin):
    list_display = ("user", "channel", "period_start", "period_end", "status")
    list_filter = ("channel", "status")
    search_fields = ("user__email",)


for _event_model in (NotificationTemplateEvent, UserNotificationSettingEvent):
    register_history(_event_model)
