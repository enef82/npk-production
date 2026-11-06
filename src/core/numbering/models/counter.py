"""Счётчик нумератора — отдельная строка на каждый период (`""` для NEVER, `"2026"` для
YEARLY). Сброс периода — это просто новая строка, а не DDL-операция над последовательностью
(обоснование выбора — `docs/adr/0009-numerator-select-for-update-ne-sequence.md`)."""

from django.db import models

from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


class NumeratorCounter(UUIDPrimaryKeyModel, TimeStampedModel):
    numerator = models.ForeignKey(
        "core_numbering.Numerator",
        on_delete=models.CASCADE,
        related_name="counters",
        verbose_name="Нумератор",
    )
    period_key = models.CharField("Ключ периода", max_length=16, blank=True)
    last_value = models.PositiveIntegerField("Последнее выданное значение", default=0)

    class Meta:
        verbose_name = "Счётчик нумератора"
        verbose_name_plural = "Счётчики нумераторов"
        constraints = [
            models.UniqueConstraint(
                fields=["numerator", "period_key"],
                name="core_numbering_counter_uniq_numerator_period",
            ),
        ]
        ordering = ["numerator", "period_key"]

    def __str__(self) -> str:
        return f"{self.numerator.code}/{self.period_key or '-'}: {self.last_value}"
