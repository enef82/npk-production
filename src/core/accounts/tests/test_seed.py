import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from src.core.accounts.groups import SEED_GROUP_NAMES
from src.core.accounts.models import User
from src.core.org.models import Department, LegalEntity


@pytest.mark.django_db
def test_seed_идемпотентен() -> None:
    # pytest-django принудительно выставляет DEBUG=False на время тестов — сама команда
    # это и проверяет отдельным тестом ниже, а здесь нужно её реальное поведение.
    with override_settings(DEBUG=True):
        call_command("seed")

        пользователей = User.objects.count()
        групп = Group.objects.count()
        юрлиц = LegalEntity.objects.count()
        подразделений = Department.objects.count()

        call_command("seed")

        assert User.objects.count() == пользователей
        assert Group.objects.count() == групп
        assert LegalEntity.objects.count() == юрлиц
        assert Department.objects.count() == подразделений


@pytest.mark.django_db
def test_seed_заводит_все_роли_включая_начальника_производства() -> None:
    with override_settings(DEBUG=True):
        call_command("seed")

    for name in SEED_GROUP_NAMES:
        assert Group.objects.filter(name=name).exists(), name
    assert Group.objects.filter(name="начальник производства").exists()


def test_seed_не_запускается_при_debug_false() -> None:
    with override_settings(DEBUG=False), pytest.raises(CommandError):
        call_command("seed")
