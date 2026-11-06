"""Подразделение. Обычный parent FK, без treebeard и materialized path — обход
потомков выполняется рекурсивным CTE в selectors.py."""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class Department(UUIDPrimaryKeyModel, TimeStampedModel):
    name = models.CharField("Наименование", max_length=255)
    code = models.CharField("Код", max_length=32, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительское подразделение",
    )
    head = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments",
        verbose_name="Руководитель",
    )
    legal_entity = models.ForeignKey(
        "core_org.LegalEntity",
        on_delete=models.PROTECT,
        related_name="departments",
        verbose_name="Юридическое лицо",
    )

    class Meta:
        verbose_name = "Подразделение"
        verbose_name_plural = "Подразделения"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
