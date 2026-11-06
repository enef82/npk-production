from .department import DepartmentCreateDTO, create_department, get_or_create_department
from .employee import EmployeeHireDTO, get_or_create_employee, hire_employee, terminate_employee
from .legal_entity import (
    LegalEntityCreateDTO,
    create_legal_entity,
    get_or_create_legal_entity,
    set_primary_legal_entity,
)
from .position import get_or_create_position

__all__ = [
    "DepartmentCreateDTO",
    "EmployeeHireDTO",
    "LegalEntityCreateDTO",
    "create_department",
    "create_legal_entity",
    "get_or_create_department",
    "get_or_create_employee",
    "get_or_create_legal_entity",
    "get_or_create_position",
    "hire_employee",
    "set_primary_legal_entity",
    "terminate_employee",
]
