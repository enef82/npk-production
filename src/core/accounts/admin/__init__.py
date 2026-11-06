"""Админка модуля «Ядро: учётные записи»."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm
from unfold.forms import UserChangeForm as UnfoldUserChangeForm
from unfold.forms import UserCreationForm as UnfoldUserCreationForm

from src.core.accounts.models import User, UserEvent  # type: ignore[attr-defined]
from src.core.audit.admin import register_history


class UserCreationForm(UnfoldUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "display_name")


class UserChangeForm(UnfoldUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):  # type: ignore[type-arg]
    add_form = UserCreationForm
    form = UserChangeForm
    change_password_form = AdminPasswordChangeForm
    model = User

    list_display = ("email", "display_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "groups")
    search_fields = ("email", "display_name")
    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Персональные данные", {"fields": ("display_name",)}),
        (
            "Права",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Даты", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Права группы — только для чтения. Единственный источник —
    `core.accounts.groups.SEED_GROUP_PERMISSIONS`, применяемый на каждом `migrate`
    через `permissions.set(...)` (перезатирает, не дополняет) — виджет, принимающий
    клик, который откатится на следующем деплое, вводит в заблуждение, а не даёт
    контроль. Членство пользователей в группах (`User.groups`) редактируется как
    раньше — это другая сущность, `sync_group_permissions` её не трогает."""

    filter_horizontal = ()
    readonly_fields = ("permissions",)


register_history(UserEvent)
