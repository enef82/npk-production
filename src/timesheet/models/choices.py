"""Перечисления модуля «Табель» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.5)."""

from django.db import models


class AllocationTarget(models.TextChoices):
    ORDER = "order", "Заказ"
    OVERHEAD = "overhead", "Накладные подразделения"
    REPAIR = "repair", "Ремонт и ТО оборудования"
    TRAINING = "training", "Обучение и аттестация"
    IDLE = "idle", "Простой"


class AllocationSource(models.TextChoices):
    MANUAL = "manual", "Вручную"
    PLAN = "plan", "По плану"
    REPAIR = "repair", "Из ремонта"


class PeriodStatus(models.TextChoices):
    DRAFT = "draft", "Заполняется"
    ON_REVIEW = "on_review", "На согласовании"
    APPROVED = "approved", "Утверждён"
    SENT = "sent", "Передан в 1С"
    CLOSED = "closed", "Закрыт"
    REOPENED = "reopened", "Открыт для корректировки"


class PeriodEventKind(models.TextChoices):
    SUBMITTED = "submitted", "Подан на согласование"
    MANAGER_CONFIRMED = "manager_confirmed", "Часы по заказам подтверждены менеджером"
    RETURNED = "returned", "Возвращён на доработку"
    APPROVED = "approved", "Утверждён"
    SENT = "sent", "Передан в 1С"
    CLOSED = "closed", "Закрыт"
    REOPENED = "reopened", "Открыт для корректировки"


class PackageType(models.TextChoices):
    TIMESHEET = "timesheet", "Табель по видам времени"
    COST_ALLOCATION = "cost_allocation", "База распределения затрат"
