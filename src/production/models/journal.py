"""Журнал заказа и утверждение документов в производство
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, «Журнал», «Документы»).

Журнал — хранимая лента, а не объединение истории при чтении (как в ИС 8а): в него
пишут и другие модули (`quality`, `supply` через `production.facade.add_journal_entry`),
и система (автостарт). Сам журнал pghistory не отслеживает — он и есть история.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import JournalKind, OrderStage
from .operation import Operation
from .order import ProductionOrder


class OrderJournalEntry(UUIDPrimaryKeyModel):
    order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name="journal",
        verbose_name="Заказ",
    )
    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="journal",
        verbose_name="Операция",
    )
    stage = models.CharField("Этап", max_length=16, choices=OrderStage.choices, blank=True)
    kind = models.CharField("Вид записи", max_length=16, choices=JournalKind.choices)
    author = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Автор",
        help_text="Пусто — запись системы",
    )
    text = models.TextField("Текст")
    # Не auto_now_add: демо-данные и перенос истории пишут запись задним числом.
    created_at = models.DateTimeField("Дата", default=timezone.now)

    class Meta:
        verbose_name = "Запись журнала заказа"
        verbose_name_plural = "Журнал заказа"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"], name="production_journal_order"),
        ]

    def __str__(self) -> str:
        return self.text[:60]


@track()
class DocumentRelease(UUIDPrimaryKeyModel, TimeStampedModel):
    """Документ утверждён в производство (отметка «кто и когда»). Аннулирование —
    снятие привязки `DocumentLink` в `core.documents`, отдельного флага здесь нет."""

    document = models.ForeignKey(
        "core_documents.Document",
        on_delete=models.PROTECT,
        related_name="production_releases",
        verbose_name="Документ",
    )
    order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name="document_releases",
        verbose_name="Заказ",
    )
    operation = models.ForeignKey(
        Operation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="document_releases",
        verbose_name="Операция",
    )
    approved_by = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="Утвердил",
    )
    approved_at = models.DateTimeField("Дата утверждения")

    class Meta:
        verbose_name = "Утверждение документа"
        verbose_name_plural = "Утверждения документов"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "order"],
                name="production_document_release_unique",
                violation_error_message="Документ уже утверждён в производство.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} → {self.order_id}"
