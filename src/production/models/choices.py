"""Перечисления модуля «Производство» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1)."""

from django.db import models


class WorkPhase(models.TextChoices):
    PREP = "prep", "Подготовка"
    PROD = "prod", "Изготовление"
    QC = "qc", "ОТК"


class OrderStage(models.TextChoices):
    LAUNCH = "launch", "Запуск в работу"
    PREP = "prep", "Подготовка производства"
    PROD = "prod", "Изготовление"
    QC = "qc", "ОТК и испытания"
    DONE = "done", "Отгружено"


# Порядок этапов — переходы только на соседний (§3.1).
ORDER_STAGE_SEQUENCE: tuple[OrderStage, ...] = (
    OrderStage.LAUNCH,
    OrderStage.PREP,
    OrderStage.PROD,
    OrderStage.QC,
    OrderStage.DONE,
)


class OperationStatus(models.TextChoices):
    WAIT = "wait", "Ожидает"
    WORK = "work", "В работе"
    CHECK = "check", "На визе"
    DONE = "done", "Выполнено"


class JournalKind(models.TextChoices):
    STAGE = "stage", "Этап"
    VISA = "visa", "Виза"
    STATUS = "status", "Статус"
    PLAN = "plan", "План"
    COMMENT = "comment", "Комментарий"
    QC = "qc", "Контроль"
    PROC = "proc", "Закупка"
    DOC = "doc", "Документ"
