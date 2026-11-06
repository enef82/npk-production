from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .document import document_upload_to


@track()
class DocumentTemplate(TimeStampedModel, UUIDPrimaryKeyModel):
    code = models.CharField("Код", max_length=64, unique=True)
    name = models.CharField("Наименование", max_length=255)
    doc_type = models.ForeignKey(
        "core_documents.DocumentType",
        verbose_name="Тип документа",
        on_delete=models.PROTECT,
        related_name="templates",
    )
    file = models.FileField("Файл шаблона (DOCX)", upload_to=document_upload_to)
    # Документирующий словарь «имя поля контекста → описание», без рантайм-валидации по
    # JSON Schema — задача требует подстановку контекста, а не его схемную проверку.
    expected_context = models.JSONField("Ожидаемый контекст", default=dict, blank=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"

    def __str__(self) -> str:
        return self.name
