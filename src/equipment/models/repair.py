"""Журнал аварий, ремонтов и ТО (§3.6).

FSM-конвенция проекта (как `production` ИС): модель объявляет голые переходы, проверки,
побочные эффекты и публикация события — в `services/repair.py`. `protected=True` не даёт
сменить статус присваиванием мимо `@transition`.

`maintenance_type` — для записи вида «ТО»: при закрытии по нему создаётся
`MaintenanceRecord`. Ссылка, а не разбор «ТО-1» из текста описания, как в прототипе.
"""

from __future__ import annotations

from django.db import models
from django.db.models import F, Q
from django_fsm import FSMField, transition

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import RepairKind, RepairStatus
from .equipment import Equipment, MaintenanceType
from .reference import FailureCategory


@track()
class Repair(UUIDPrimaryKeyModel, TimeStampedModel):
    number = models.CharField("Номер", max_length=32, unique=True)
    equipment = models.ForeignKey(
        Equipment, on_delete=models.PROTECT, related_name="repairs", verbose_name="Оборудование"
    )
    kind = models.CharField("Вид", max_length=16, choices=RepairKind.choices)
    maintenance_type = models.ForeignKey(
        MaintenanceType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="repairs",
        verbose_name="Вид ТО",
    )
    started_at = models.DateTimeField("Начало простоя")
    finished_at = models.DateTimeField("Окончание простоя", null=True, blank=True)
    category = models.ForeignKey(
        FailureCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="repairs",
        verbose_name="Категория отказа",
    )
    alarm_code = models.CharField("Код аварии (SCADA / ЧПУ)", max_length=32, blank=True)
    description = models.TextField("Что произошло / работы")
    fix = models.TextField("Что сделано, причина", blank=True)
    parts = models.TextField("Запчасти и материалы", blank=True)
    status = FSMField(
        "Статус",
        max_length=16,
        choices=RepairStatus.choices,
        default=RepairStatus.OPEN,
        protected=True,
    )

    class Meta:
        verbose_name = "Авария / ремонт"
        verbose_name_plural = "Аварии и ремонты"
        ordering = ["-started_at"]
        constraints = [
            models.CheckConstraint(
                name="equipment_repair_finish_after_start",
                condition=Q(finished_at__isnull=True) | Q(finished_at__gte=F("started_at")),
                violation_error_message="Окончание простоя раньше начала.",
            ),
            models.CheckConstraint(
                name="equipment_repair_done_has_finish",
                condition=~Q(status=RepairStatus.DONE) | Q(finished_at__isnull=False),
                violation_error_message="Закрытая запись обязана иметь окончание простоя.",
            ),
            # По категории строится статистика отказов — закрыть аварию без неё нельзя.
            models.CheckConstraint(
                name="equipment_repair_failure_category",
                condition=(
                    ~Q(kind=RepairKind.FAILURE, status=RepairStatus.DONE)
                    | Q(category__isnull=False)
                ),
                violation_error_message="Укажите категорию отказа.",
            ),
            models.CheckConstraint(
                name="equipment_repair_maintenance_type",
                condition=(
                    Q(kind=RepairKind.MAINTENANCE, maintenance_type__isnull=False)
                    | (~Q(kind=RepairKind.MAINTENANCE) & Q(maintenance_type__isnull=True))
                ),
                violation_error_message="Вид ТО указывается у записи вида «ТО» и только у неё.",
            ),
        ]
        indexes = [
            models.Index(fields=["equipment", "-started_at"], name="equipment_repair_by_eq"),
            models.Index(fields=["status"], name="equipment_repair_status"),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.get_kind_display()}"

    @transition(field=status, source=RepairStatus.OPEN, target=RepairStatus.IN_WORK)
    def mark_in_work(self) -> None:
        pass

    @transition(
        field=status, source=[RepairStatus.OPEN, RepairStatus.IN_WORK], target=RepairStatus.DONE
    )
    def mark_done(self) -> None:
        pass


@track()
class RepairWorker(UUIDPrimaryKeyModel, TimeStampedModel):
    repair = models.ForeignKey(
        Repair, on_delete=models.CASCADE, related_name="workers", verbose_name="Ремонт"
    )
    employee = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="repair_works",
        verbose_name="Сотрудник",
    )
    hours = models.DecimalField("Часы", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Исполнитель ремонта"
        verbose_name_plural = "Исполнители ремонта"
        ordering = ["repair", "employee__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["repair", "employee"],
                name="equipment_repair_worker_unique",
                violation_error_message="Сотрудник уже указан в этом ремонте.",
            ),
            models.CheckConstraint(
                name="equipment_repair_worker_hours_positive",
                condition=Q(hours__gt=0),
                violation_error_message="Часы исполнителя должны быть больше нуля.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id}: {self.hours} ч"
