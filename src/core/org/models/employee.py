"""Сотрудник. Живёт в core.org, а не в hr — предикаты прав в core.accounts должны знать
подразделение сотрудника, а импортировать hr из ядра запрещено (инвариант И1)."""

from django.conf import settings
from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import EmployeeStatus


@track()
class Employee(UUIDPrimaryKeyModel, TimeStampedModel):
    full_name = models.CharField("ФИО", max_length=255)
    personnel_number = models.CharField("Табельный номер", max_length=32, unique=True)
    department = models.ForeignKey(
        "core_org.Department",
        on_delete=models.PROTECT,
        related_name="employees",
        verbose_name="Подразделение",
    )
    position = models.ForeignKey(
        "core_org.Position",
        on_delete=models.PROTECT,
        related_name="employees",
        verbose_name="Должность",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee",
        verbose_name="Пользователь",
    )
    hire_date = models.DateField("Дата приёма")
    termination_date = models.DateField("Дата увольнения", null=True, blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=EmployeeStatus.choices, default=EmployeeStatus.ACTIVE
    )

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.personnel_number})"
