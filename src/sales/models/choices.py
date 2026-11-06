"""Перечисления модуля «Заявки и калькуляция» (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.2)."""

from django.db import models


class InquiryStage(models.TextChoices):
    NEW = "new", "Новые заявки"
    CALC = "calc", "Просчёт"
    APPROVAL = "approval", "Согласование КП"
    LAUNCHED = "launched", "Запущена в работу"
    LOST = "lost", "Проиграна"


# Этапы с визами — переходы только на соседний (§3.2).
INQUIRY_STAGE_SEQUENCE: tuple[InquiryStage, ...] = (
    InquiryStage.NEW,
    InquiryStage.CALC,
    InquiryStage.APPROVAL,
)
OPEN_STAGES = INQUIRY_STAGE_SEQUENCE
