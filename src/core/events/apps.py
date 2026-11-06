from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core.events"
    label = "core_events"
    verbose_name = "Ядро: события"

    def ready(self) -> None:
        from django.utils.module_loading import autodiscover_modules

        autodiscover_modules("handlers")
