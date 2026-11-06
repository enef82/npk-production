"""Хелпер для регистрации read-only списка истории Event-модели (созданной `tracking.track()`)
в админке любого модуля — единообразно, вместо того чтобы каждый модуль писал свой
`ModelAdmin` для истории заново."""

from __future__ import annotations

from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin


def register_history(event_model: type[models.Model]) -> None:
    if admin.site.is_registered(event_model):
        return

    field_names = {f.name for f in event_model._meta.fields}
    list_display = [
        name for name in ("pgh_created_at", "pgh_label", "pgh_obj") if name in field_names
    ]

    admin_class = type(
        f"{event_model.__name__}Admin",
        (ModelAdmin,),
        {
            "list_display": list_display,
            "list_filter": ["pgh_label"] if "pgh_label" in field_names else [],
            "ordering": ["-pgh_created_at"] if "pgh_created_at" in field_names else [],
            "has_add_permission": lambda self, request: False,
            "has_change_permission": lambda self, request, obj=None: False,
            "has_delete_permission": lambda self, request, obj=None: False,
        },
    )
    admin.site.register(event_model, admin_class)
