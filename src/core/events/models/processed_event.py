"""Журнал обработанных событий — основа идемпотентности обработчиков."""

from django.db import models

from .outbox_event import OutboxEvent


class ProcessedEvent(models.Model):
    event = models.ForeignKey(
        OutboxEvent,
        verbose_name="Событие",
        on_delete=models.CASCADE,
        related_name="processed_by",
    )
    handler_name = models.CharField("Обработчик", max_length=255)
    processed_at = models.DateTimeField("Время обработки", auto_now_add=True)

    class Meta:
        verbose_name = "Обработанное событие"
        verbose_name_plural = "Обработанные события"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "handler_name"],
                name="core_events_processedevent_uniq_event_handler",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_id} / {self.handler_name}"
