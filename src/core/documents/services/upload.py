"""Загрузка файла: проверка типа/размера, подсчёт контрольной суммы, привязка к сущности.

Единственное место транзакций для создания Document при первой загрузке.

Проверка типа — **запрещающий список**, а не разрешающий: пустой `DocumentType.allowed_mime_types`
означает «любой тип, кроме исполняемых» (спецификация CRM ИС §3.10). Перечислить заранее всё,
что пришлют с заявкой (`dwg`, `rar`, `7z`, `p7s`, …), нельзя, а пустой разрешающий список —
типовая ловушка: он естественно читается как «ничего не разрешено», и загрузка молча падает
на всём. Непустой `allowed_mime_types` работает как прежде — строгий разрешающий список
(так устроен тип шаблона КП: только DOCX и PDF).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from uuid6 import uuid7

from src.core.common.exceptions import ValidationError
from src.core.documents.models import Document, DocumentLink, DocumentType

# Исполняемые: блокируются всегда, когда тип документа не задаёт свой разрешающий список.
# Проверяется и расширение (браузерный content_type ненадёжен), и MIME.
FORBIDDEN_UPLOAD_EXTENSIONS = frozenset(
    {
        ".exe",
        ".msi",
        ".msix",
        ".com",
        ".scr",
        ".bat",
        ".cmd",
        ".pif",
        ".ps1",
        ".psm1",
        ".vbs",
        ".vbe",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".sh",
        ".bash",
        ".zsh",
        ".ksh",
        ".run",
        ".bin",
        ".app",
        ".dll",
        ".sys",
        ".drv",
        ".cpl",
        ".ocx",
        ".scf",
        ".msc",
        ".jar",
        ".apk",
        ".appx",
        ".deb",
        ".rpm",
        ".dmg",
    }
)
FORBIDDEN_UPLOAD_MIME_TYPES = frozenset(
    {
        "application/x-msdownload",
        "application/x-msdos-program",
        "application/x-dosexec",
        "application/x-executable",
        "application/x-elf",
        "application/x-mach-binary",
        "application/vnd.microsoft.portable-executable",
        "application/x-sh",
        "application/x-shellscript",
        "application/x-bat",
        "application/x-msi",
        "application/java-archive",
        "application/vnd.android.package-archive",
    }
)

_MB = 1024 * 1024


@dataclass(frozen=True)
class DocumentUploadDTO:
    file: UploadedFile
    doc_type_code: str
    uploaded_by: UUID
    entity_type: str = ""
    entity_id: UUID | None = None
    role: str = ""
    description: str = ""


@dataclass(frozen=True)
class StoredUpload:
    """Файл, уже записанный в объектное хранилище (до транзакции вызывающего сервиса).

    Строку `Document` для него создаёт `persist_upload` внутри транзакции вызывающего.
    Если та транзакция откатится, объект останется в бакете без ссылающегося `Document` —
    его убирает регламентная задача `core_documents.sweep_orphaned_storage_objects`.
    """

    document_id: UUID
    storage_name: str
    original_name: str
    size_bytes: int
    mime_type: str
    checksum: str
    doc_type_code: str


def checksum_of(file: UploadedFile) -> str:
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()


def _is_forbidden_executable(file: UploadedFile, content_type: str) -> bool:
    extension = PurePosixPath(file.name or "").suffix.lower()
    return extension in FORBIDDEN_UPLOAD_EXTENSIONS or content_type in FORBIDDEN_UPLOAD_MIME_TYPES


def validate_against_doc_type(file: UploadedFile, doc_type: DocumentType) -> tuple[str, int]:
    """Проверяет тип и размер, возвращает (MIME-тип, размер). Общая проверка для первой
    загрузки и для новой версии — тип документа между версиями не меняется."""

    content_type = file.content_type or ""
    if doc_type.allowed_mime_types:
        if content_type not in doc_type.allowed_mime_types:
            raise ValidationError(f"Тип файла «{content_type}» недопустим для «{doc_type.name}».")
    elif _is_forbidden_executable(file, content_type):
        raise ValidationError(
            f"Файл «{file.name}» распознан как исполняемый — такие вложения не принимаются."
        )

    if file.size is None:
        raise ValidationError("Не удалось определить размер файла.")
    if file.size > doc_type.max_size_bytes:
        raise ValidationError(
            f"Файл «{file.name}» — {file.size / _MB:.1f} МБ, это больше лимита "
            f"{doc_type.max_size_bytes / _MB:.0f} МБ для «{doc_type.name}». "
            f"Уменьшите файл или разбейте комплект на части."
        )
    return content_type, file.size


def _storage_key(document_id: UUID, filename: str) -> str:
    # Тот же формат, что document_upload_to: documents/<document_id>/<filename>. Ключ
    # включает id документа — по нему регламентная уборка отличает осиротевший объект.
    return f"documents/{document_id}/{filename or 'file'}"


def store_upload(file: UploadedFile, *, doc_type_code: str) -> StoredUpload:
    """Проверяет файл и пишет его в объектное хранилище **до** транзакции вызывающего
    сервиса. Запись в MinIO не откатывается вместе с транзакцией (спецификация CRM ИС
    §3.10), поэтому она вынесена наружу, а не спрятана в `Document.objects.create`."""

    doc_type = DocumentType.objects.get(code=doc_type_code, is_active=True)
    content_type, size = validate_against_doc_type(file, doc_type)
    checksum = checksum_of(file)

    document_id = uuid7()
    storage_name = default_storage.save(_storage_key(document_id, file.name or ""), file)
    return StoredUpload(
        document_id=document_id,
        storage_name=storage_name,
        original_name=file.name or "",
        size_bytes=size,
        mime_type=content_type,
        checksum=checksum,
        doc_type_code=doc_type_code,
    )


def persist_upload(
    stored: StoredUpload,
    *,
    uploaded_by: UUID,
    description: str = "",
    change_note: str = "",
    supersedes: Document | None = None,
) -> Document:
    """Создаёт строку `Document` для уже загруженного файла — вызывается **внутри**
    транзакции вызывающего сервиса. Привязку к сущности делает вызывающий отдельно
    (`attach_document`): `core.documents` не знает entity_type функциональных модулей."""

    doc_type = DocumentType.objects.get(code=stored.doc_type_code, is_active=True)
    return Document.objects.create(
        id=stored.document_id,
        original_name=stored.original_name,
        description=description,
        change_note=change_note,
        file=stored.storage_name,
        size_bytes=stored.size_bytes,
        mime_type=stored.mime_type,
        checksum=stored.checksum,
        doc_type=doc_type,
        uploaded_by=uploaded_by,
        version=(supersedes.version + 1) if supersedes is not None else 1,
        supersedes=supersedes,
    )


def upload_document(data: DocumentUploadDTO) -> Document:
    doc_type = DocumentType.objects.get(code=data.doc_type_code, is_active=True)
    content_type, size = validate_against_doc_type(data.file, doc_type)
    checksum = checksum_of(data.file)

    with transaction.atomic():
        document = Document.objects.create(
            original_name=data.file.name or "",
            description=data.description,
            file=data.file,
            size_bytes=size,
            mime_type=content_type,
            checksum=checksum,
            doc_type=doc_type,
            uploaded_by=data.uploaded_by,
        )

        if data.entity_type and data.entity_id is not None:
            DocumentLink.objects.create(
                document=document,
                entity_type=data.entity_type,
                entity_id=data.entity_id,
                role=data.role,
            )

    return document
