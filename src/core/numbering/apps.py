from django.apps import AppConfig


class NumberingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core.numbering"
    label = "core_numbering"
    verbose_name = "Ядро: нумерация"
