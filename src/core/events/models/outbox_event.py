"""Outbox — таблица событий, записываемых в той же транзакции, что и изменение состояния."""

from django.db import models


class OutboxEvent(models.Model):
    event_type = models.CharField("Тип события", max_length=255, db_index=True)
    version = models.PositiveSmallIntegerField("Версия схемы", default=1)
    aggregate_id = models.UUIDField("Идентификатор агрегата")
    payload = models.JSONField("Данные события", default=dict)
    occurred_at = models.DateTimeField("Время наступления", auto_now_add=True)
    processed_at = models.DateTimeField("Время обработки", null=True, blank=True, db_index=True)
    next_attempt_at = models.DateTimeField(
        "Время следующей попытки", null=True, blank=True, db_index=True
    )
    attempts = models.PositiveIntegerField("Число попыток", default=0)
    last_error = models.TextField("Последняя ошибка", blank=True)

    class Meta:
        verbose_name = "Событие (outbox)"
        verbose_name_plural = "События (outbox)"
        indexes = [
            models.Index(
                fields=["event_type", "occurred_at"],
                name="core_events_type_occurred",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} #{self.pk}"
