from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


def document_upload_to(instance: "Document", filename: str) -> str:
    # instance.id генерируется UUIDPrimaryKeyModel до сохранения (default=uuid7), поэтому
    # ключ уникален уже на этапе построения пути — коллизии между документами исключены.
    return f"documents/{instance.id}/{filename}"


@track()
class Document(TimeStampedModel, UUIDPrimaryKeyModel):
    original_name = models.CharField("Имя файла", max_length=255)
    # Свободное описание файла вместо справочника типов вложений (спецификация CRM ИС §3.10,
    # docs/adr/0016-vlozheniya-bez-spravochnika-tipov-i-antivirusa.md): «ТЗ ред. 2», «архив ПД».
    # Поле на документе, а не на привязке: описание принадлежит файлу и переезжает с ним,
    # если тот же комплект позже привяжется к договору.
    description = models.CharField("Описание", max_length=255, blank=True)
    file = models.FileField("Файл", upload_to=document_upload_to)
    size_bytes = models.BigIntegerField("Размер, байт")
    mime_type = models.CharField("MIME-тип", max_length=128)
    checksum = models.CharField("Контрольная сумма (SHA-256)", max_length=64, db_index=True)
    doc_type = models.ForeignKey(
        "core_documents.DocumentType",
        verbose_name="Тип документа",
        on_delete=models.PROTECT,
        related_name="documents",
    )
    version = models.PositiveSmallIntegerField("Версия", default=1)
    # Что изменилось в этой редакции относительно предыдущей (спецификация CRM ИС §3.10).
    # Пустой у первой загрузки, обязателен при перевыпуске: реестр редакций без описания
    # изменений бесполезен. Ссылку на официальное письмо сюда не писать — по CLAUDE.md §5
    # письмо всегда запись журнала переписки (срез 1б), а не текст «по письму № …».
    change_note = models.TextField("Лист изменений", blank=True)
    supersedes = models.ForeignKey(
        "self",
        verbose_name="Предыдущая версия",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )
    # actor_id без FK на User — core.documents ниже core.accounts в слоевом контракте
    # не обязан быть, но связь через голый UUID здесь единообразна с остальным ядром
    # (Delegation.created_by, ApprovalRequest.started_by).
    uploaded_by = models.UUIDField("Кто загрузил")

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def __str__(self) -> str:
        return f"{self.original_name} (v{self.version})"
