"""Увольнение закрывает доступ: связанная учётная запись отключается вместе со статусом
сотрудника. Приём на работу, наоборот, не включает учётку автоматически — возврат
доступа должен быть отдельным осознанным действием."""

from datetime import date

import pytest

from src.core.accounts.tests.factories import UserFactory
from src.core.org import facade as org
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory, PositionFactory


@pytest.mark.django_db
def test_увольнение_отключает_учётную_запись() -> None:
    user = UserFactory(is_active=True)
    employee = EmployeeFactory(user=user)
    employee_id = employee.id  # type: ignore[attr-defined]

    org.terminate_employee(
        employee_id,
        termination_date=date(2026, 8, 20),
        actor_id=employee_id,
    )

    user.refresh_from_db()  # type: ignore[attr-defined]
    assert user.is_active is False


@pytest.mark.django_db
def test_приём_на_работу_не_включает_отключённую_учётную_запись() -> None:
    user = UserFactory(is_active=False)
    user_id = user.id  # type: ignore[attr-defined]
    department = DepartmentFactory()
    position = PositionFactory()

    org.hire_employee(
        org.EmployeeHireDTO(
            full_name="Сидоров Сидор Сидорович",
            personnel_number="99999",
            department_id=department.id,  # type: ignore[attr-defined]
            position_id=position.id,  # type: ignore[attr-defined]
            hire_date=date(2026, 1, 1),
            user_id=user_id,
        )
    )

    user.refresh_from_db()  # type: ignore[attr-defined]
    assert user.is_active is False
