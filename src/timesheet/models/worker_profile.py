"""Профиль работника — расширение `core.org.Employee` 1:1 (CLAUDE.md §5: первичный ключ —
сам внешний ключ на сотрудника).

Табельного номера здесь нет, хотя спецификация §3.5 называет `personnel_no`: у
`Employee` уже есть уникальный `personnel_number`, и вторая копия разошлась бы с ним
на первой правке — а в пакет 1С уходит ровно один номер
(`docs/adr/0041-timesheet-tabelnyy-nomer-i-svyaz-s-production.md`).
`work_center_id` — UUID участка модуля `production` без внешнего ключа (И2).
"""

from django.db import models
from django.db.models import Q

from src.core.audit.tracking import track
from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel


@track()
class WorkerProfile(TimeStampedModel):
    employee = models.OneToOneField(
        "core_org.Employee",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="worker_profile",
        verbose_name="Сотрудник",
    )
    work_center_id = models.UUIDField("Участок", null=True, blank=True)
    hourly_rate = MoneyField(verbose_name="Часовая ставка")

    class Meta:
        verbose_name = "Профиль работника"
        verbose_name_plural = "Профили работников"
        ordering = ["employee__full_name"]
        constraints = [
            models.CheckConstraint(
                name="timesheet_worker_rate_not_negative",
                condition=Q(hourly_rate__gte=0),
                violation_error_message="Часовая ставка не может быть отрицательной.",
            ),
        ]

    def __str__(self) -> str:
        return str(self.employee_id)
