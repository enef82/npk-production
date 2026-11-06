"""Табель подразделения за месяц и журнал его переходов.

FSM-конвенция проекта: модель объявляет голые переходы, проверки и журнал — в
`services/period.py`. Период заводится лениво, при первом обращении: «нет записи» и
«черновик версии 1» для экрана одно и то же.

Визы менеджеров по своим заказам — строки журнала `MANAGER_CONFIRMED`, а не поле
периода: действуют визы, поставленные после последней подачи на согласование, так что
возврат и переоткрытие снимают их без отдельного сброса.

`TimesheetPeriod` без `@track()`: pghistory назвал бы свою модель истории
`TimesheetPeriodEvent` — имя журнала из спецификации. Аудит периода — сам журнал:
каждый переход пишется сервисом с автором, версией и причиной.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django_fsm import FSMField, transition

from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import PeriodEventKind, PeriodStatus


class TimesheetPeriod(UUIDPrimaryKeyModel, TimeStampedModel):
    department = models.ForeignKey(
        "core_org.Department",
        on_delete=models.PROTECT,
        related_name="timesheet_periods",
        verbose_name="Подразделение",
    )
    month = models.DateField("Месяц", help_text="Первое число месяца")
    status = FSMField(
        "Статус",
        max_length=16,
        choices=PeriodStatus.choices,
        default=PeriodStatus.DRAFT,
        protected=True,
    )
    version = models.PositiveSmallIntegerField("Версия", default=1)

    class Meta:
        verbose_name = "Табель подразделения"
        verbose_name_plural = "Табели подразделений"
        ordering = ["-month", "department__name"]
        permissions = [
            ("edit_department", "Правка разноски своего подразделения"),
            ("edit_any", "Правка разноски любого подразделения"),
            ("approve_period", "Согласование табеля и передача в 1С"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "month"],
                name="timesheet_period_unique_department_month",
                violation_error_message="Табель подразделения за этот месяц уже есть.",
            ),
            models.CheckConstraint(
                name="timesheet_period_month_first_day",
                condition=Q(month__day=1),
                violation_error_message="Месяц табеля задаётся первым числом.",
            ),
            models.CheckConstraint(
                name="timesheet_period_version_positive",
                condition=Q(version__gte=1),
                violation_error_message="Версия табеля начинается с 1.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.department_id} {self.month:%m.%Y} v{self.version}"

    @transition(
        field=status,
        source=[PeriodStatus.DRAFT, PeriodStatus.REOPENED],
        target=PeriodStatus.ON_REVIEW,
    )
    def mark_submitted(self) -> None:
        pass

    @transition(field=status, source=PeriodStatus.ON_REVIEW, target=PeriodStatus.DRAFT)
    def mark_returned_to_draft(self) -> None:
        pass

    @transition(field=status, source=PeriodStatus.ON_REVIEW, target=PeriodStatus.REOPENED)
    def mark_returned_to_reopened(self) -> None:
        pass

    @transition(field=status, source=PeriodStatus.ON_REVIEW, target=PeriodStatus.APPROVED)
    def mark_approved(self) -> None:
        pass

    @transition(field=status, source=PeriodStatus.APPROVED, target=PeriodStatus.SENT)
    def mark_sent(self) -> None:
        pass

    @transition(field=status, source=PeriodStatus.SENT, target=PeriodStatus.CLOSED)
    def mark_closed(self) -> None:
        pass

    @transition(
        field=status,
        source=[PeriodStatus.SENT, PeriodStatus.CLOSED],
        target=PeriodStatus.REOPENED,
    )
    def mark_reopened(self) -> None:
        pass


class TimesheetPeriodEvent(UUIDPrimaryKeyModel, TimeStampedModel):
    """Журнал переходов периода и виз менеджеров. Пишется только сервисом, не правится:
    это история, а не состояние."""

    period = models.ForeignKey(
        TimesheetPeriod,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Табель",
    )
    kind = models.CharField("Событие", max_length=32, choices=PeriodEventKind.choices)
    version = models.PositiveSmallIntegerField("Версия табеля")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Кто",
    )
    manager = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Менеджер",
    )
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Событие табеля"
        verbose_name_plural = "Журнал табеля"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                name="timesheet_period_event_manager",
                condition=(Q(kind=PeriodEventKind.MANAGER_CONFIRMED) & Q(manager__isnull=False))
                | (~Q(kind=PeriodEventKind.MANAGER_CONFIRMED) & Q(manager__isnull=True)),
                violation_error_message="Менеджер указывается только у визы менеджера.",
            ),
            models.CheckConstraint(
                name="timesheet_period_event_reason",
                condition=~Q(kind__in=[PeriodEventKind.RETURNED, PeriodEventKind.REOPENED])
                | ~Q(comment=""),
                violation_error_message="Возврат и переоткрытие табеля — только с причиной.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.period_id}: {self.kind}"
