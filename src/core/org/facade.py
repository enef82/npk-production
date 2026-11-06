"""Публичный интерфейс модуля «Ядро: организационная структура» для других модулей.

Используется прежде всего `core.accounts.rules` (предикаты прав должны знать
подразделение сотрудника) и командой `core.accounts` `seed` (демо-оргструктура).
`core.org` лежит ниже `core.accounts` в слоевом контракте (`.importlinter`), поэтому
направление зависимости — только отсюда наверх.
"""

from __future__ import annotations

from uuid import UUID

from src.core.org.selectors import (
    EmployeeBrief,
    get_department_by_code,
    get_employee,
    get_employee_by_user,
    get_primary_legal_entity,
    list_active_employees,
    list_department_and_descendant_ids,
    list_departments_headed_by,
)
from src.core.org.services import (
    DepartmentCreateDTO,
    EmployeeHireDTO,
    LegalEntityCreateDTO,
    create_department,
    create_legal_entity,
    get_or_create_department,
    get_or_create_employee,
    get_or_create_legal_entity,
    get_or_create_position,
    hire_employee,
    set_primary_legal_entity,
    terminate_employee,
)

__all__ = [
    "DepartmentCreateDTO",
    "EmployeeBrief",
    "EmployeeHireDTO",
    "LegalEntityCreateDTO",
    "create_department",
    "create_legal_entity",
    "get_department_by_code",
    "get_department_id_for_employee",
    "get_department_id_for_user",
    "get_employee_by_user",
    "get_user_id_for_employee",
    "get_or_create_department",
    "get_or_create_employee",
    "get_or_create_legal_entity",
    "get_or_create_position",
    "get_primary_legal_entity",
    "hire_employee",
    "list_active_employees",
    "list_department_and_descendant_ids",
    "list_departments_headed_by",
    "set_primary_legal_entity",
    "terminate_employee",
]


def get_department_id_for_user(user_id: UUID) -> UUID | None:
    employee = get_employee_by_user(user_id)
    return employee.department_id if employee else None


def get_department_id_for_employee(employee_id: UUID) -> UUID | None:
    employee = get_employee(employee_id)
    return employee.department_id if employee else None


def get_user_id_for_employee(employee_id: UUID) -> UUID | None:
    employee = get_employee(employee_id)
    return employee.user_id if employee else None
