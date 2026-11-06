"""Регистрация шаблонов генерации — идемпотентный upsert `DocumentType` + `DocumentTemplate`.

Единственное место транзакций для заведения шаблона из кода. Вызывается прод-сидами
прикладных модулей (`crm.management.commands.seed_crm`): сам прикладной модуль таблицы
`core.documents` не пишет (И3), а миграция для этого не годится — `DocumentTemplate.file`
хранится в объектном хранилище через django-storages, и запись в него из миграции
привязала бы применение схемы к доступности MinIO (ADR 0015 ИС (генерация КП)).
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction

from src.core.documents.models import DocumentTemplate, DocumentType
from src.core.documents.services.generation import DOCX_MIME_TYPE, PDF_MIME_TYPE

_DEFAULT_MAX_SIZE_BYTES = 20 * 1024 * 1024


def register_generation_template(
    *,
    template_code: str,
    template_name: str,
    doc_type_code: str,
    doc_type_name: str,
    content: bytes,
    filename: str,
    expected_context: dict[str, str],
    allowed_mime_types: list[str] | None = None,
    max_size_bytes: int = _DEFAULT_MAX_SIZE_BYTES,
) -> DocumentTemplate:
    """Заводит или обновляет тип документа и DOCX-шаблон под этим типом. Файл шаблона
    перезаписывается только при первом заведении или при изменении содержимого — повторный
    прогон сида не плодит осиротевшие объекты в хранилище (`AWS_S3_FILE_OVERWRITE=False`)."""

    mimes = allowed_mime_types or [DOCX_MIME_TYPE, PDF_MIME_TYPE]

    with transaction.atomic():
        doc_type, _ = DocumentType.objects.update_or_create(
            code=doc_type_code,
            defaults={
                "name": doc_type_name,
                "allowed_mime_types": mimes,
                "max_size_bytes": max_size_bytes,
                "is_active": True,
            },
        )
        template, _ = DocumentTemplate.objects.update_or_create(
            code=template_code,
            defaults={
                "name": template_name,
                "doc_type": doc_type,
                "expected_context": expected_context,
                "is_active": True,
            },
        )

        needs_upload = True
        if template.file:
            try:
                with template.file.open("rb") as current:
                    needs_upload = current.read() != content
            except FileNotFoundError:
                needs_upload = True
        if needs_upload:
            template.file.save(filename, ContentFile(content), save=True)

    return template
