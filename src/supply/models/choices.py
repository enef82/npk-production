"""Перечисления модуля «Снабжение и склад» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4)."""

from django.db import models


class LineKind(models.TextChoices):
    MATERIAL = "mat", "Материалы и комплектующие"
    TOOL = "tool", "Оснастка, инструмент, расходники"


class LineCategory(models.TextChoices):
    MATERIAL = "material", "Материал"
    TOOL = "tool", "Инструмент"
    FIXTURE = "fixture", "Оснастка"
    CONSUMABLE = "consumable", "Расходники"


class LineStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    SENT = "sent", "Передано в закупку"
    ORDERED = "ordered", "Заказано"
    RECEIVED = "received", "Принято на склад"
    RESERVED = "reserved", "Резерв со склада"
    ISSUED = "issued", "Передано в производство"


# Строка «закрыта» для опоздания (`PR_DONE` прототипа): материал уже на складе или в цехе.
CLOSED_STATUSES: tuple[LineStatus, ...] = (
    LineStatus.RECEIVED,
    LineStatus.RESERVED,
    LineStatus.ISSUED,
)
