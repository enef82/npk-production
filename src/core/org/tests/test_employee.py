"""Статусные переходы Employee, включая запрещённые, и ограничения БД."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from src.core.common.exceptions import ConflictError
from src.core.org.models import EmployeeStatus
from src.core.org.services import terminate_employee
from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory, LegalEntityFactory


@pytest.mark.django_db
def test_увольнение_переводит_сотрудника_в_статус_уволен() -> None:
    сотрудник = EmployeeFactory()
    сотрудник_id = сотрудник.id  # type: ignore[attr-defined]

    terminate_employee(сотрудник_id, termination_date=date(2026, 8, 20), actor_id=сотрудник_id)

    сотрудник.refresh_from_db()  # type: ignore[attr-defined]
    assert сотрудник.status == EmployeeStatus.DISMISSED
    assert сотрудник.termination_date == date(2026, 8, 20)  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_нельзя_повторно_уволить_уволенного_сотрудника() -> None:
    сотрудник = EmployeeFactory(status=EmployeeStatus.DISMISSED, termination_date=date(2025, 1, 1))
    сотрудник_id = сотрудник.id  # type: ignore[attr-defined]

    with pytest.raises(ConflictError):
        terminate_employee(сотрудник_id, termination_date=date(2026, 8, 20), actor_id=сотрудник_id)


@pytest.mark.django_db
def test_увольнение_снимает_сотрудника_с_руководителя_подразделения() -> None:
    руководитель = EmployeeFactory()
    подразделение = DepartmentFactory(head=руководитель)
    руководитель_id = руководитель.id  # type: ignore[attr-defined]

    terminate_employee(
        руководитель_id, termination_date=date(2026, 8, 20), actor_id=руководитель_id
    )

    подразделение.refresh_from_db()  # type: ignore[attr-defined]
    assert подразделение.head_id is None  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_увольнение_снимает_сотрудника_с_подписанта_по_умолчанию() -> None:
    подписант = EmployeeFactory()
    юрлицо = LegalEntityFactory(default_signatory=подписант)
    подписант_id = подписант.id  # type: ignore[attr-defined]

    terminate_employee(подписант_id, termination_date=date(2026, 8, 20), actor_id=подписант_id)

    юрлицо.refresh_from_db()  # type: ignore[attr-defined]
    assert юрлицо.default_signatory_id is None  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_табельный_номер_уникален() -> None:
    EmployeeFactory(personnel_number="00001")

    with pytest.raises(IntegrityError), transaction.atomic():
        EmployeeFactory(personnel_number="00001")


@pytest.mark.django_db
def test_код_подразделения_уникален() -> None:
    DepartmentFactory(code="dept-x")

    with pytest.raises(IntegrityError), transaction.atomic():
        DepartmentFactory(code="dept-x")
