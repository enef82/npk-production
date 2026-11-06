"""Статусные и типовые перечисления оргструктуры."""

from django.db import models


class TaxSystem(models.TextChoices):
    OSN = "osn", "ОСН"
    USN_INCOME = "usn_income", "УСН доходы"
    USN_INCOME_MINUS_EXPENSES = "usn_income_minus_expenses", "УСН доходы минус расходы"
    ESHN = "eshn", "ЕСХН"
    PATENT = "patent", "ПСН"


class PositionCategory(models.TextChoices):
    WORKER = "worker", "Рабочий"
    SPECIALIST = "specialist", "Специалист"
    EMPLOYEE = "employee", "Служащий"
    MANAGER = "manager", "Руководитель"


class EmployeeStatus(models.TextChoices):
    ACTIVE = "active", "Работает"
    DISMISSED = "dismissed", "Уволен"
