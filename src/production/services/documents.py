"""Документы заказа: загрузка с видом, привязка к заказу и операции, утверждение в
производство, аннулирование (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1,
«Документы»).

Файл хранит `core.documents`; привязка — `DocumentLink(entity_type="production.order" |
"production.operation")`. Документ операции привязан и к заказу: список документов
заказа — один запрос, операция видна по второй привязке. Аннулирование — снятие
привязок (отдельного флага нет, §3.1).
"""

from __future__ import annotations

from uuid import UUID

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.documents import facade as documents
from src.production.exceptions import DocumentNotLinked, DocumentTypeInvalid, OperationMismatch
from src.production.models import DocumentRelease, JournalKind, Operation, ProductionOrder
from src.production.selectors import (
    DOCUMENT_TYPE_CODES,
    OPERATION_ENTITY,
    ORDER_ENTITY,
    document_type_name,
)
from src.production.services.common import journal, lock_order


def upload_order_document(
    order_id: UUID,
    file: UploadedFile,
    *,
    doc_type_code: str,
    operation_id: UUID | None,
    description: str = "",
    actor_id: UUID,
    actor_employee_id: UUID | None,
) -> UUID:
    if doc_type_code not in DOCUMENT_TYPE_CODES:
        raise DocumentTypeInvalid
    if (
        operation_id is not None
        and not Operation.objects.filter(id=operation_id, order_id=order_id).exists()
    ):
        raise OperationMismatch
    # Запись в хранилище — до транзакции: она не откатывается вместе с БД
    # (`core.documents.services.upload.store_upload`).
    stored = documents.store_upload(file, doc_type_code=doc_type_code)
    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        document = documents.persist_upload(
            stored, uploaded_by=actor_id, description=description.strip()
        )
        documents.attach_document(document.id, ORDER_ENTITY, order.id)
        operation = None
        if operation_id is not None:
            operation = Operation.objects.get(id=operation_id)
            documents.attach_document(document.id, OPERATION_ENTITY, operation_id)
        journal(
            order,
            JournalKind.DOC,
            f"Загружен документ «{document.original_name}» ({document_type_name(doc_type_code)})",
            operation=operation,
            author_id=actor_employee_id,
        )
    return document.id


def _linked_operation(order: ProductionOrder, document_id: UUID) -> Operation | None:
    operation_ids = list(Operation.objects.filter(order=order).values_list("id", flat=True))
    link = documents.DocumentLink.objects.filter(
        document_id=document_id, entity_type=OPERATION_ENTITY, entity_id__in=operation_ids
    ).first()
    return Operation.objects.get(id=link.entity_id) if link is not None else None


def _ensure_linked(order: ProductionOrder, document_id: UUID) -> None:
    if not documents.DocumentLink.objects.filter(
        document_id=document_id, entity_type=ORDER_ENTITY, entity_id=order.id
    ).exists():
        raise DocumentNotLinked


def approve_document(
    order_id: UUID, document_id: UUID, *, actor_id: UUID, approver_id: UUID
) -> None:
    """Утверждение документа в производство — отметка «кто и когда». Повторное
    утверждение ничего не меняет."""

    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        _ensure_linked(order, document_id)
        if DocumentRelease.objects.filter(document_id=document_id, order=order).exists():
            return
        operation = _linked_operation(order, document_id)
        DocumentRelease.objects.create(
            document_id=document_id,
            order=order,
            operation=operation,
            approved_by_id=approver_id,
            approved_at=timezone.now(),
        )
        document = documents.get_document(document_id)
        journal(
            order,
            JournalKind.DOC,
            f"Документ «{document.original_name if document else ''}» утверждён в производство",
            operation=operation,
            author_id=approver_id,
        )


def annul_document(
    order_id: UUID, document_id: UUID, *, actor_id: UUID, actor_employee_id: UUID | None
) -> None:
    with transaction.atomic(), actor_context(actor_id):
        order = lock_order(order_id)
        _ensure_linked(order, document_id)
        operation = _linked_operation(order, document_id)
        document = documents.get_document(document_id)
        documents.detach_document_chain(ORDER_ENTITY, order.id, document_id)
        if operation is not None:
            documents.detach_document_chain(OPERATION_ENTITY, operation.id, document_id)
        DocumentRelease.objects.filter(document_id=document_id, order=order).delete()
        journal(
            order,
            JournalKind.DOC,
            f"Документ «{document.original_name if document else ''}» аннулирован",
            operation=operation,
            author_id=actor_employee_id,
        )
