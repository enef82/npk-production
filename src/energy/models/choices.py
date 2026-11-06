"""Перечисления модуля «Энергоучёт» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.7)."""

from django.db import models


class MeterKind(models.TextChoices):
    INPUT = "input", "Ввод"
    NODE = "node", "Узел"
    SHOP = "shop", "Цех / участок"
    EQUIPMENT = "equipment", "Оборудование"
    COMPRESSOR = "compressor", "Компрессорная"
    OFFICE = "office", "АБК и офис"
    OTHER = "other", "Прочее"


class MeterSource(models.TextChoices):
    SCADA = "scada", "SCADA"
    MANUAL = "manual", "Вручную"
