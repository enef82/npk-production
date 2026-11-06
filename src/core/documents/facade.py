"""Публичный интерфейс модуля «Ядро: документы» для других модулей.

Вызывающий модуль отвечает за собственную проверку прав по своей сущности (см.
`core.documents.rules` — модуль не знает entity_type функциональных модулей и поэтому не
может проверить доступ к ним сам). Привязка к сущности — только строковая пара
(entity_type, entity_id), без ForeignKey и без contenttypes.
"""

from __future__ import annotations

from src.core.documents.models import Document, DocumentLink, DocumentTemplate, DocumentType
from src.core.documents.registry import register_entity_visibility_checker
from src.core.documents.selectors import (
    get_attached_chain_top,
    get_current_version,
    get_document,
    get_document_template,
    get_download_url,
    get_version_chain_ids,
    is_previewable,
    list_attachments_for_entity,
    list_current_for_entity,
    list_versions,
)
from src.core.documents.services import (
    DOCX_MIME_TYPE,
    PDF_MIME_TYPE,
    DocumentUploadDTO,
    StoredUpload,
    attach_document,
    detach_document,
    detach_document_chain,
    persist_upload,
    register_generation_template,
    render_docx_from_template,
    render_template_to_docx,
    render_to_pdf,
    store_generated_document,
    store_upload,
    upload_document,
    upload_new_version,
    upsert_document_type,
)

__all__ = [
    "DOCX_MIME_TYPE",
    "PDF_MIME_TYPE",
    "Document",
    "DocumentLink",
    "DocumentTemplate",
    "DocumentType",
    "DocumentUploadDTO",
    "StoredUpload",
    "attach_document",
    "detach_document",
    "detach_document_chain",
    "get_attached_chain_top",
    "get_current_version",
    "get_document",
    "get_document_template",
    "get_download_url",
    "get_version_chain_ids",
    "is_previewable",
    "list_attachments_for_entity",
    "list_current_for_entity",
    "list_versions",
    "persist_upload",
    "register_entity_visibility_checker",
    "register_generation_template",
    "render_docx_from_template",
    "render_template_to_docx",
    "render_to_pdf",
    "store_generated_document",
    "store_upload",
    "upload_document",
    "upload_new_version",
    "upsert_document_type",
]
