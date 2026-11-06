from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import UUIDPrimaryKeyModel


@track()
class DocumentLink(UUIDPrimaryKeyModel):
    """Привязка документа к произвольной сущности. Без contenttypes и GenericForeignKey —
    только строковый (entity_type, entity_id), чтобы core.documents не знал о существовании
    ни одного функционального модуля (см. CLAUDE.md, docs/spec/03-platforma.md §1)."""

    document = models.ForeignKey(
        "core_documents.Document",
        verbose_name="Документ",
        on_delete=models.CASCADE,
        related_name="links",
    )
    entity_type = models.CharField("Тип сущности", max_length=64, db_index=True)
    entity_id = models.UUIDField("Идентификатор сущности", db_index=True)
    # Свободная строка, не TextChoices: набор ролей открыт для любого будущего модуля,
    # и core.documents не должен править свой код ради нового значения (скан/оригинал/приложение
    # из docs/spec/03-platforma.md §2.1 — только примеры, не исчерпывающий список).
    role = models.CharField("Роль", max_length=32, blank=True)

    class Meta:
        verbose_name = "Привязка документа"
        verbose_name_plural = "Привязки документов"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "entity_type", "entity_id", "role"],
                name="core_documents_link_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} → {self.entity_type}:{self.entity_id}"
