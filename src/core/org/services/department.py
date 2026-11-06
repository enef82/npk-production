"""Создание подразделений. Единственное место транзакций для Department."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from src.core.org.models import Department


@dataclass(frozen=True)
class DepartmentCreateDTO:
    name: str
    code: str
    legal_entity_id: UUID
    parent_id: UUID | None = None
    head_id: UUID | None = None


def create_department(data: DepartmentCreateDTO) -> Department:
    with transaction.atomic():
        department = Department.objects.create(
            name=data.name,
            code=data.code,
            legal_entity_id=data.legal_entity_id,
            parent_id=data.parent_id,
            head_id=data.head_id,
        )

    return department


def get_or_create_department(data: DepartmentCreateDTO) -> Department:
    """Для идемпотентного сида: естественный ключ — `code`."""

    with transaction.atomic():
        department, _ = Department.objects.get_or_create(
            code=data.code,
            defaults={
                "name": data.name,
                "legal_entity_id": data.legal_entity_id,
                "parent_id": data.parent_id,
                "head_id": data.head_id,
            },
        )

    return department
