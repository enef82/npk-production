"""Привязка и отвязка документа от произвольной сущности. Единственное место транзакций
для DocumentLink."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from src.core.documents.models import DocumentLink
from src.core.documents.selectors import get_version_chain_ids


def attach_document(
    document_id: UUID, entity_type: str, entity_id: UUID, role: str = ""
) -> DocumentLink:
    with transaction.atomic():
        link, _ = DocumentLink.objects.get_or_create(
            document_id=document_id,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        )
    return link


def detach_document(document_id: UUID, entity_type: str, entity_id: UUID, role: str = "") -> None:
    with transaction.atomic():
        DocumentLink.objects.filter(
            document_id=document_id,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        ).delete()


def detach_document_chain(entity_type: str, entity_id: UUID, document_id: UUID) -> int:
    """Снимает привязку **всей цепочки версий** документа к сущности — открепить одну
    редакцию, оставив предыдущие висеть в списке заявки, смысла нет (спецификация CRM ИС (IS_ERP, 10-crm)
    §3.10, «открепление удаляет привязку»). Ни один `Document` и ни одна его версия не
    удаляются. Возвращает число снятых привязок (0 — цепочка к сущности не привязана)."""

    chain_ids = get_version_chain_ids(document_id)
    if not chain_ids:
        return 0
    with transaction.atomic():
        deleted, _ = DocumentLink.objects.filter(
            document_id__in=chain_ids, entity_type=entity_type, entity_id=entity_id
        ).delete()
    return deleted
