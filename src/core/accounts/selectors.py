"""Запросы на чтение и агрегаты модуля «Ядро: учётные записи»."""

from __future__ import annotations

from uuid import UUID

from django.contrib.auth.models import Permission
from django.db.models import Q

from src.core.accounts.models import User


def list_user_ids_with_perm(perm: str) -> list[UUID]:
    """Идентификаторы активных пользователей, у которых есть право `perm`
    («<app>.<codename>») — как суперпользователь, напрямую или через группу. Нужен
    рассылке уведомлений держателям права
    (`core.costing.services.work_norm.notify_expiring_work_norms`): адресат — роль,
    а не конкретный человек.

    Своя выборка, а не `UserManager.with_perm`: кастомный `UserManager` наследует
    `BaseUserManager`, где этого метода нет. Логика совпадает с `ModelBackend`.
    """

    app_label, _, codename = perm.partition(".")
    try:
        permission = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    except Permission.DoesNotExist:
        return []

    holders = (
        Q(is_superuser=True) | Q(user_permissions=permission) | Q(groups__permissions=permission)
    )
    return list(
        User.objects.filter(holders, is_active=True).distinct().values_list("id", flat=True)
    )
