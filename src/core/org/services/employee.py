"""Приём и увольнение сотрудников. Единственное место транзакций для Employee."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction

from src.core.common.exceptions import ConflictError
from src.core.org.models import Department, Employee, EmployeeStatus, LegalEntity


@dataclass(frozen=True)
class EmployeeHireDTO:
    full_name: str
    personnel_number: str
    department_id: UUID
    position_id: UUID
    hire_date: date
    user_id: UUID | None = None


def hire_employee(data: EmployeeHireDTO) -> Employee:
    with transaction.atomic():
        employee = Employee.objects.create(
            full_name=data.full_name,
            personnel_number=data.personnel_number,
            department_id=data.department_id,
            position_id=data.position_id,
            hire_date=data.hire_date,
            user_id=data.user_id,
            status=EmployeeStatus.ACTIVE,
        )

    return employee


def get_or_create_employee(data: EmployeeHireDTO) -> Employee:
    """Для идемпотентного сида: естественный ключ — `personnel_number`."""

    with transaction.atomic():
        employee, _ = Employee.objects.get_or_create(
            personnel_number=data.personnel_number,
            defaults={
                "full_name": data.full_name,
                "department_id": data.department_id,
                "position_id": data.position_id,
                "hire_date": data.hire_date,
                "user_id": data.user_id,
                "status": EmployeeStatus.ACTIVE,
            },
        )

    return employee


def terminate_employee(employee_id: UUID, *, termination_date: date, actor_id: UUID) -> None:
    """Увольняет сотрудника и закрывает его доступ: если к сотруднику привязана учётная
    запись, она отключается (`is_active=False`) в той же транзакции. Обратное — включение
    учётки при приёме — сервис `hire_employee` не делает: возврат доступа должен быть
    отдельным осознанным действием, а не побочным эффектом заполнения анкеты.

    Заодно снимает уволенного с ролей «руководитель подразделения» и «подписант по
    умолчанию» — `on_delete=SET_NULL` на этих FK защищает только от удаления записи
    Employee, а увольнение её не удаляет, только меняет статус. Без явной очистки
    подразделение или юрлицо молча остаётся с уволенным сотрудником в этих ролях."""

    with transaction.atomic():
        employee = Employee.objects.select_for_update().get(id=employee_id)
        if employee.status == EmployeeStatus.DISMISSED:
            raise ConflictError("Сотрудник уже уволен.")
        employee.status = EmployeeStatus.DISMISSED
        employee.termination_date = termination_date
        employee.save(update_fields=["status", "termination_date", "updated_at"])

        Department.objects.filter(head_id=employee.id).update(head=None)
        LegalEntity.objects.filter(default_signatory_id=employee.id).update(default_signatory=None)

        if employee.user_id is not None:
            # get_user_model(), не facade/событие: core.org лежит ниже core.accounts
            # (.importlinter, core-layers), прямой импорт запрещён. Это осознанное узкое
            # исключение (CLAUDE.md §3, И1) — отзыв доступа обязан быть атомарным с
            # увольнением в одной транзакции, а событие из core.events асинхронное
            # (диспетчер тикает раз в EVENTS_DISPATCH_INTERVAL_SECONDS) и не гарантирует
            # обработку. Не превращай это в прецедент: для всего остального связь между
            # модулями ядра — через facade или событие, а не через get_user_model().
            get_user_model().objects.filter(id=employee.user_id).update(is_active=False)
