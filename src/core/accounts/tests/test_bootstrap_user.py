from io import StringIO
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth.hashers import is_password_usable
from django.core.management import call_command
from django.core.management.base import CommandError

from src.core.accounts.groups import PROJECT_MANAGER
from src.core.accounts.models import User
from src.core.identity import facade as identity
from src.core.org import facade as org
from src.core.org.models import Department, PositionCategory, TaxSystem


@pytest.fixture
def department() -> Department:
    party = identity.create_party(
        identity.PartyCreateDTO(
            inn="7700000099",
            legal_name="Тестовое юрлицо",
            short_name="Тест",
            party_type=identity.PartyType.LEGAL,
        ),
        actor_id=uuid4(),
    )
    legal_entity = org.get_or_create_legal_entity(
        org.LegalEntityCreateDTO(party_id=party.id, print_name="Тест", tax_system=TaxSystem.OSN)
    )
    return org.get_or_create_department(
        org.DepartmentCreateDTO(
            name="Производство", code="test-dept", legal_entity_id=legal_entity.pk
        )
    )


def _call(department_code: str, **overrides: Any) -> StringIO:
    out = StringIO()
    args = {
        "email": "ivanov@npk-prod.local",
        "display_name": "Иванов И.И.",
        "full_name": "Иванов Иван Иванович",
        "personnel_number": "00099",
        "department_code": department_code,
        "position": "Инженер ПНР",
        "position_category": PositionCategory.SPECIALIST.value,
        "role": PROJECT_MANAGER,
    }
    args.update(overrides)
    call_command("bootstrap_user", stdout=out, **args)
    return out


@pytest.mark.django_db
def test_заводит_пользователя_сотрудника_и_роль(department: Department) -> None:
    out = _call(department.code)

    user = User.objects.get(email="ivanov@npk-prod.local")
    assert user.is_active is True
    assert is_password_usable(user.password)
    assert user.groups.filter(name=PROJECT_MANAGER).exists()

    employee = org.get_employee_by_user(user.id)
    assert employee is not None
    assert employee.full_name == "Иванов Иван Иванович"
    assert employee.department_id == department.id

    assert "Пароль" in out.getvalue()


@pytest.mark.django_db
def test_пароль_не_совпадает_с_email_и_не_пустой(department: Department) -> None:
    _call(department.code)

    user = User.objects.get(email="ivanov@npk-prod.local")
    assert not user.check_password("")
    assert not user.check_password("ivanov@npk-prod.local")


@pytest.mark.django_db
def test_повторный_вызов_на_тот_же_email_не_перезаписывает_пароль(department: Department) -> None:
    _call(department.code)
    user_before = User.objects.get(email="ivanov@npk-prod.local")
    password_hash_before = user_before.password

    with pytest.raises(CommandError):
        _call(department.code)

    user_after = User.objects.get(email="ivanov@npk-prod.local")
    assert user_after.password == password_hash_before


@pytest.mark.django_db
def test_несуществующее_подразделение_даёт_понятную_ошибку() -> None:
    with pytest.raises(CommandError, match="не найдено"):
        _call("нет-такого-кода")


@pytest.mark.django_db
def test_superuser_всегда_получает_is_staff(department: Department) -> None:
    _call(department.code, superuser=True)

    user = User.objects.get(email="ivanov@npk-prod.local")
    assert user.is_superuser is True
    assert user.is_staff is True
