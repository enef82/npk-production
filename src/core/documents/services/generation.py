"""Генерация документов: рендер DOCX из шаблона (docxtpl) и конвертация в PDF.

Рендер и сохранение разведены намеренно (`render_template_to_docx` → байты,
`store_generated_document` → `Document`): вызывающий модуль, которому нужны и DOCX, и
PDF, обязан получить обе конвертации **до** записи в БД, чтобы отказ Gotenberg всплывал
там, где причина (у генерации), а не при скачивании, и не оставлял в хранилище
半-готовый комплект. `render_docx_from_template` — композиция обеих для простого случая
«отрендерил и сохранил один файл».

Конвертация DOCX→PDF изолирована в одной функции `render_to_pdf` — единственном месте,
которое знает о Gotenberg (docs/adr/0008-docxtpl-i-gotenberg-dlya-generatsii-dokumentov.md,
ADR 0015 ИС (генерация КП)). Замена движка конвертации — правка только
этой функции.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any
from uuid import UUID

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from docxtpl import DocxTemplate

from src.core.documents.models import Document, DocumentTemplate, DocumentType

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME_TYPE = "application/pdf"


def _load_active_template(template_id: UUID) -> DocumentTemplate:
    return DocumentTemplate.objects.select_related("doc_type").get(id=template_id, is_active=True)


def _render(template: DocumentTemplate, context: dict[str, Any]) -> bytes:
    with template.file.open("rb") as source:
        tpl = DocxTemplate(BytesIO(source.read()))
    tpl.render(context)
    rendered = BytesIO()
    tpl.save(rendered)
    return rendered.getvalue()


def render_template_to_docx(template_id: UUID, context: dict[str, Any]) -> bytes:
    """Рендерит DOCX-шаблон с подстановкой контекста и возвращает байты. В БД не пишет —
    сохранение отдельным вызовом `store_generated_document` (см. докстринг модуля)."""

    return _render(_load_active_template(template_id), context)


def store_generated_document(
    content: bytes,
    *,
    original_name: str,
    mime_type: str,
    doc_type: DocumentType,
    actor_id: UUID,
    supersedes: Document | None = None,
) -> Document:
    """Сохраняет уже отрендеренные байты как `Document`. `supersedes` задан — новая версия
    (`version + 1`), старый файл и его привязки остаются (см. `services/versioning.py`);
    привязки новой версии проставляет вызывающий."""

    with transaction.atomic():
        return Document.objects.create(
            original_name=original_name,
            file=ContentFile(content, name=original_name),
            size_bytes=len(content),
            mime_type=mime_type,
            checksum=hashlib.sha256(content).hexdigest(),
            doc_type=doc_type,
            uploaded_by=actor_id,
            version=(supersedes.version + 1) if supersedes is not None else 1,
            supersedes=supersedes,
        )


def render_docx_from_template(
    template_id: UUID, context: dict[str, Any], *, actor_id: UUID
) -> Document:
    template = _load_active_template(template_id)
    content = _render(template, context)
    return store_generated_document(
        content,
        original_name=f"{template.name}.docx",
        mime_type=DOCX_MIME_TYPE,
        doc_type=template.doc_type,
        actor_id=actor_id,
    )


def render_to_pdf(docx_bytes: bytes, *, filename: str = "document.docx") -> bytes:
    response = httpx.post(
        f"{settings.GOTENBERG_URL}/forms/libreoffice/convert",
        files={"files": (filename, docx_bytes, DOCX_MIME_TYPE)},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.content
