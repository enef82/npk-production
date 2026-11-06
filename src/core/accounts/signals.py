"""Выдача прикладных разрешений ролям при `migrate` (`groups.SEED_GROUP_PERMISSIONS`).

`sync_group_permissions` подключён к `post_migrate` **без фильтра по `sender`**, поэтому
срабатывает после каждого приложения. Объекты `Permission` создаёт свой, отдельный
`post_migrate`-приёмник Django (`django.contrib.auth.management.create_permissions`),
по одному приложению за раз — право прикладного модуля может ещё не существовать в тот
момент, когда наш приёмник вызван на раннем приложении. Такое право в этом firing просто
не попадает в набор для `set(...)`; к последнему приложению существуют все права, и
`set(...)` на этом firing даёт окончательный, полный состав. Промежуточное сужение
между firing'ами одного `migrate` не наблюдаемо снаружи — команда не возвращает
управление до последнего.

То же самообновление закрывает и `flush()` транзакционных тестов: Django после `flush`
эмитит `post_migrate` (пере-создаёт content types и permissions), а вместе с ним снова
отрабатывает и этот приёмник — восстанавливая и роль, и связку роль→право. Отдельная
autouse-фикстура, как для RunPython-посева (`conftest.ensure_core_reference_data`), тут
не нужна: RunPython повторно не запускается, а этот код — запускается.

**`set(...)`, не `add(...)` — карта перезатирает, а не дополняет.** Право, выданное
группе кликом в Django Admin мимо карты, будет снято на следующем `migrate`; право,
отозванное кликом, но заданное в карте, будет восстановлено. `groups.py` объясняет,
почему это осознанный выбор, а не недосмотр: единственный источник правды — репозиторий,
а не база плюс то, что в ней накликали. Отсюда и требование карты называть каждую роль
явно, даже пустым набором (см. там же) — иначе роль вне карты осталась бы вне `set(...)`
и копила бы права, о которых репозиторий не знает.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest

from src.core.accounts.groups import SEED_GROUP_PERMISSIONS

logger = logging.getLogger(__name__)


def _client_ip(request: HttpRequest) -> str:
    # Caddy — единственный обратный прокси перед Django (ADR 0029), доверяем первому
    # адресу в X-Forwarded-For. REMOTE_ADDR за прокси — адрес самого Caddy, бесполезен
    # для журнала неудачных входов.
    forwarded: str | None = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return str(forwarded.split(",")[0].strip())
    return str(request.META.get("REMOTE_ADDR", "unknown"))


def log_failed_login(
    sender: Any,
    credentials: dict[str, Any],
    request: HttpRequest | None = None,
    **kwargs: Any,
) -> None:
    """docs/adr/0030-publikatsiya-v-internet.md, мера 5: без этого журнала условие
    пересмотра решения о полной публикации в интернет невыполнимо — нельзя заметить
    серию неудачных входов, которую никто не записывает. Django сам вырезает пароль
    из `credentials` до отправки сигнала (`_clean_credentials`), поэтому это не
    отдельная проверка, а штатное поведение сигнала."""

    email = credentials.get("username", "<нет>")
    ip = _client_ip(request) if request is not None else "unknown"
    logger.warning("Неудачная попытка входа: email=%s ip=%s", email, ip)


def sync_group_permissions(*args: Any, **kwargs: Any) -> None:
    from django.contrib.auth.models import Group, Permission

    for group_name, permission_labels in SEED_GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        resolved: list[int] = []
        for label in permission_labels:
            app_label, codename = label.split(".", 1)
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is None:
                continue
            resolved.append(permission.pk)
        group.permissions.set(resolved)
