"""Выдача прикладных разрешений ролям (`groups.SEED_GROUP_PERMISSIONS`,
`signals.sync_group_permissions`) — единственный механизм привязки права `has_perm(...)`
к `Group`. Роль-членство проверяют `is_*`-предикаты, но `can_*`-предикаты спрашивают
разрешение, и до этого механизма оно группе ниоткуда не доставалось.

Карта — единственный источник правды, не один из нескольких: `sync_group_permissions`
перезатирает (`permissions.set(...)`), а не дополняет. Правка через Django Admin не
переживает следующий `migrate` — оба направления дрейфа (право, добавленное мимо
карты; право, отозванное из карты) проверены ниже explicit."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.test import Client

from src.core.accounts.groups import SEED_GROUP_NAMES, SEED_GROUP_PERMISSIONS
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory


def _role_with_permissions() -> tuple[str, tuple[str, ...]]:
    """Роль с непустым набором прав из карты — тесты механизма не завязаны на то,
    какой именно модуль какие права раздаёт."""

    for name, labels in SEED_GROUP_PERMISSIONS.items():
        if labels:
            return name, labels
    pytest.skip("в карте ещё нет ни одной роли с правами")


@pytest.mark.django_db
def test_sync_привязывает_каждое_право_из_карты_к_своей_группе() -> None:
    sync_group_permissions()  # в норме уже отработал на post_migrate; идемпотентен

    for group_name, permission_labels in SEED_GROUP_PERMISSIONS.items():
        group = Group.objects.get(name=group_name)
        for label in permission_labels:
            app_label, codename = label.split(".", 1)
            assert group.permissions.filter(
                content_type__app_label=app_label, codename=codename
            ).exists(), f"{label} не выдано группе {group_name}"


@pytest.mark.django_db
def test_sync_идемпотентен() -> None:
    role, _ = _role_with_permissions()
    sync_group_permissions()
    group = Group.objects.get(name=role)
    before = group.permissions.count()

    sync_group_permissions()

    assert Group.objects.get(name=role).permissions.count() == before


@pytest.mark.django_db
def test_каждое_право_из_карты_реально_существует() -> None:
    """Опечатка в `SEED_GROUP_PERMISSIONS`  молча не
    выдала бы ничего — `sync` пропускает несуществующее право. Ловим на этапе теста."""

    for permission_labels in SEED_GROUP_PERMISSIONS.values():
        for label in permission_labels:
            app_label, codename = label.split(".", 1)
            assert Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).exists(), f"право {label} не определено ни в одной модели"


def test_карта_называет_каждую_роль_явно() -> None:
    """Роль, не упомянутая в карте вовсе (даже пустым набором), осталась бы вне
    `sync_group_permissions` — не «прав нет», а «мы не знаем», и то, что накопилось
    в базе снаружи карты, никогда бы не тронулось (`groups.py`, докстринг модуля)."""

    assert set(SEED_GROUP_PERMISSIONS.keys()) == set(SEED_GROUP_NAMES)


@pytest.mark.django_db
def test_sync_убирает_право_выданное_группе_мимо_карты() -> None:
    """Право, добавленное кликом в админке помимо карты, не переживает `migrate`
    (`groups.py`: карта — единственный источник, а не один из нескольких)."""

    role, labels = _role_with_permissions()
    sync_group_permissions()
    group = Group.objects.get(name=role)
    mapped_labels = set(labels)
    stray = Permission.objects.exclude(
        content_type__app_label__in={label.split(".", 1)[0] for label in mapped_labels},
        codename__in={label.split(".", 1)[1] for label in mapped_labels},
    ).first()
    assert stray is not None
    group.permissions.add(stray)

    sync_group_permissions()

    assert not Group.objects.get(name=role).permissions.filter(pk=stray.pk).exists()


@pytest.mark.django_db
def test_sync_восстанавливает_право_отозванное_из_группы() -> None:
    """Право, снятое кликом в админке, но заданное в карте, возвращается на следующем
    `migrate` — состояние прав определяется репозиторием, не базой конкретного
    окружения (`groups.py`)."""

    role, labels = _role_with_permissions()
    sync_group_permissions()
    group = Group.objects.get(name=role)
    app_label, codename = labels[0].split(".", 1)
    mapped = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    group.permissions.remove(mapped)
    assert not group.permissions.filter(pk=mapped.pk).exists()

    sync_group_permissions()

    assert Group.objects.get(name=role).permissions.filter(pk=mapped.pk).exists()


@pytest.mark.django_db
def test_права_группы_только_для_чтения_в_админке() -> None:
    """Виджет прав на странице группы читает `filter_horizontal`/`readonly_fields`
    (`core.accounts.admin.GroupAdmin`) — редактируемый POST по `permissions` не должен
    доходить до `Group.permissions`, иначе клик выглядел бы решением, которое откатится
    на следующем деплое."""

    sync_group_permissions()
    admin_user: User = UserFactory(is_staff=True, is_superuser=True)  # type: ignore[assignment]
    client = Client()
    client.force_login(admin_user)
    group = Group.objects.get(name=_role_with_permissions()[0])
    before = set(group.permissions.values_list("pk", flat=True))

    response = client.post(
        f"/admin/auth/group/{group.pk}/change/",
        {"name": group.name, "permissions": []},
    )

    assert response.status_code in (200, 302)
    after = set(Group.objects.get(pk=group.pk).permissions.values_list("pk", flat=True))
    assert after == before
