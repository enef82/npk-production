"""Новая версия документа. Единственное место транзакций для версионирования Document.

Новая версия никогда не затирает предыдущую: создаётся новый Document с version + 1 и
ссылкой supersedes, старый файл и его DocumentLink остаются как есть, а его привязки
дублируются на новую версию — тот же набор (entity_type, entity_id, role) продолжает
указывать на актуальный документ.
"""

from __future__ import annotations

from uuid import UUID

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from src.core.documents.models import Document, DocumentLink
from src.core.documents.services.upload import checksum_of, validate_against_doc_type


def upload_new_version(document_id: UUID, file: UploadedFile, *, actor_id: UUID) -> Document:
    previous = Document.objects.select_related("doc_type").get(id=document_id)
    content_type, size = validate_against_doc_type(file, previous.doc_type)
    checksum = checksum_of(file)

    with transaction.atomic():
        new_version = Document.objects.create(
            original_name=file.name or previous.original_name,
            file=file,
            size_bytes=size,
            mime_type=content_type,
            checksum=checksum,
            doc_type=previous.doc_type,
            version=previous.version + 1,
            supersedes=previous,
            uploaded_by=actor_id,
        )
        DocumentLink.objects.bulk_create(
            [
                DocumentLink(
                    document=new_version,
                    entity_type=link.entity_type,
                    entity_id=link.entity_id,
                    role=link.role,
                )
                for link in previous.links.all()
            ]
        )

    return new_version
