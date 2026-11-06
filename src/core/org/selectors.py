"""Запросы на чтение и агрегаты модуля «Ядро: организационная структура»."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import connection

from src.core.org.models import Department, Employee, EmployeeStatus, LegalEntity

_DESCENDANTS_SQL = """
WITH RECURSIVE subtree AS (
    SELECT id FROM core_org_department WHERE id = %s
    UNION ALL
    SELECT d.id
    FROM core_org_department d
    JOIN subtree s ON d.parent_id = s.id
)
SELECT id FROM subtree
"""


def get_department(department_id: UUID) -> Department | None:
    return Department.objects.filter(id=department_id).first()


def get_department_by_code(code: str) -> Department | None:
    """Для команд бутстрапа: подразделение адресуется естественным ключом (`code`),
    не UUID, который оператор команды не помнит наизусть."""

    return Department.objects.filter(code=code).first()


def get_employee(employee_id: UUID) -> Employee | None:
    return Employee.objects.filter(id=employee_id).first()


def get_employee_by_user(user_id: UUID) -> Employee | None:
    return Employee.objects.filter(user_id=user_id).first()


@dataclass(frozen=True)
class EmployeeBrief:
    id: UUID
    full_name: str


def list_active_employees() -> list[EmployeeBrief]:
    """Работающие сотрудники (id + ФИО) для пикеров и фильтров прикладных модулей —
    первый потребитель — фильтр реестра заявок `crm` по ответственному
    (спец. CRM ИС §7). Только два поля: модель `Employee` наружу не отдаём (И1)."""

    rows = (
        Employee.objects.filter(status=EmployeeStatus.ACTIVE)
        .order_by("full_name")
        .values_list("id", "full_name")
    )
    return [EmployeeBrief(id=row[0], full_name=row[1]) for row in rows]


def get_legal_entity(legal_entity_id: UUID) -> LegalEntity | None:
    return LegalEntity.objects.filter(pk=legal_entity_id).first()


def get_primary_legal_entity() -> LegalEntity | None:
    """Основная организация для печатных форм (шапка КП — `crm`, шаг 10). Признак
    `is_primary` уникален частичным ограничением, поэтому запись не больше одной."""

    return LegalEntity.objects.filter(is_primary=True).first()


def list_department_and_descendant_ids(department_id: UUID) -> list[UUID]:
    """Подразделение и все его потомки любой глубины, рекурсивным CTE."""

    with connection.cursor() as cursor:
        cursor.execute(_DESCENDANTS_SQL, [str(department_id)])
        return [row[0] for row in cursor.fetchall()]


def list_departments_headed_by(user_id: UUID) -> list[UUID]:
    employee = get_employee_by_user(user_id)
    if employee is None:
        return []
    return list(Department.objects.filter(head_id=employee.id).values_list("id", flat=True))
