"""Перечисления модуля «Оборудование и ТО» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.6)."""

from django.db import models


class EquipmentStatus(models.TextChoices):
    RUN = "run", "Работает"
    IDLE = "idle", "Простаивает"
    MAINTENANCE = "to", "На ТО"
    REPAIR = "repair", "В ремонте"


class RuntimeSource(models.TextChoices):
    MANUAL = "manual", "Вручную"
    SCADA = "scada", "SCADA"


class RepairKind(models.TextChoices):
    FAILURE = "fail", "Авария"
    REPAIR = "repair", "Плановый ремонт"
    MAINTENANCE = "maintenance", "ТО"


class RepairStatus(models.TextChoices):
    OPEN = "open", "Зарегистрирована"
    IN_WORK = "work", "В ремонте"
    DONE = "done", "Устранено"


class MaintenanceState(models.TextChoices):
    """Состояние ТО — выводится селектором (`toState` прототипа), не хранится."""

    OVERDUE = "overdue", "Просрочено"
    SOON = "soon", "Скоро (остаток меньше 10 % интервала)"
    OK = "ok", "Норма"
