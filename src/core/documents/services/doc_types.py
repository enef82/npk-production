"""Идемпотентный upsert `DocumentType` из кода.

Отдельно от `templates.register_generation_template` (тот заводит тип **под шаблон
генерации** и всегда с непустым списком MIME): здесь заводится тип-носитель ограничений
для загружаемых пользователем файлов — вложения заявки (спецификация CRM ИС (IS_ERP, 10-crm) §3.10),
где `allowed_mime_types` пустой («любой, кроме исполняемых»).

Командой, а не data-миграцией, по тому же правилу, что и шаблон КП
(ADR 0015 ИС (генерация КП)): тип документа — справочные данные, которые
правит администратор (лимит размера меняется в админке без релиза), и в истории миграций
это выглядело бы изменением схемы.
"""

from __future__ import annotations

from src.core.documents.models import DocumentType


def upsert_document_type(
    *,
    code: str,
    name: str,
    max_size_bytes: int,
    allowed_mime_types: list[str] | None = None,
) -> DocumentType:
    doc_type, _ = DocumentType.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "max_size_bytes": max_size_bytes,
            "allowed_mime_types": allowed_mime_types or [],
            "is_active": True,
        },
    )
    return doc_type
