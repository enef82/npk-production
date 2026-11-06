"""Предикаты прав: allow и deny по отдельности для каждого."""

import pytest
from django.contrib.auth.models import Group

from src.core.accounts.groups import ADMINISTRATOR
from src.core.accounts.rules import (
    in_same_department_or_below,
    is_administrator,
    is_department_head,
    is_own_record,
)
from src.core.accounts.tests.factories import UserFactory
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory


@pytest.mark.django_db
def test_суперпользователь_является_администратором() -> None:
    assert is_administrator(UserFactory(is_superuser=True)) is True


@pytest.mark.django_db
def test_рядовой_пользователь_не_администратор() -> None:
    assert is_administrator(UserFactory()) is False


@pytest.mark.django_db
def test_пользователь_из_группы_администратор_является_администратором() -> None:
    group, _ = Group.objects.get_or_create(name=ADMINISTRATOR)
    user = UserFactory()
    user.groups.add(group)  # type: ignore[attr-defined]

    assert is_administrator(user) is True


@pytest.mark.django_db
def test_is_own_record_для_своей_учётной_записи() -> None:
    user = UserFactory()
    assert is_own_record(user, user) is True


@pytest.mark.django_db
def test_is_own_record_для_чужой_учётной_записи() -> None:
    assert is_own_record(UserFactory(), UserFactory()) is False


@pytest.mark.django_db
def test_is_department_head_для_руководителя_подразделения() -> None:
    root = DepartmentFactory()
    руководитель = UserFactory()
    глава = EmployeeFactory(department=root, user=руководитель)
    root.head = глава  # type: ignore[assignment]
    root.save(update_fields=["head"])  # type: ignore[attr-defined]

    assert is_department_head(руководитель, root.id) is True  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_is_department_head_для_рядового_сотрудника() -> None:
    root = DepartmentFactory()
    user = UserFactory()
    EmployeeFactory(department=root, user=user)

    assert is_department_head(user, root.id) is False  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_руководитель_видит_подразделение_и_все_дочерние() -> None:
    root = DepartmentFactory()
    child = DepartmentFactory(parent=root, legal_entity=root.legal_entity)
    grandchild = DepartmentFactory(parent=child, legal_entity=root.legal_entity)
    сосед = DepartmentFactory(legal_entity=root.legal_entity)

    руководитель = UserFactory()
    глава = EmployeeFactory(department=root, user=руководитель)
    root.head = глава  # type: ignore[assignment]
    root.save(update_fields=["head"])  # type: ignore[attr-defined]

    сотрудник_внук = EmployeeFactory(department=grandchild)
    сотрудник_соседнего_подразделения = EmployeeFactory(department=сосед)

    assert in_same_department_or_below(руководитель, сотрудник_внук) is True
    assert in_same_department_or_below(руководитель, сотрудник_соседнего_подразделения) is False


@pytest.mark.django_db
def test_рядовой_сотрудник_не_видит_чужое_подразделение_как_руководитель() -> None:
    root = DepartmentFactory()
    user = UserFactory()
    EmployeeFactory(department=root, user=user)
    чужой_сотрудник = EmployeeFactory(department=root)

    assert in_same_department_or_below(user, чужой_сотрудник) is False
