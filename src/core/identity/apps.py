from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core.identity"
    label = "core_identity"
    verbose_name = "Ядро: идентичность"
