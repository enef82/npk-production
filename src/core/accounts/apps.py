from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core.accounts"
    label = "core_accounts"
    verbose_name = "Ядро: учётные записи"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_login_failed
        from django.db.models.signals import post_migrate

        from src.core.accounts.signals import log_failed_login, sync_group_permissions

        post_migrate.connect(
            sync_group_permissions,
            dispatch_uid="core_accounts.sync_group_permissions",
        )
        # Технический журнал, не бизнес-логика — исключение из запрета §5 на сигналы
        # (docs/adr/0030-publikatsiya-v-internet.md, мера 5).
        user_login_failed.connect(
            log_failed_login,
            dispatch_uid="core_accounts.log_failed_login",
        )
