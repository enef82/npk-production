"""Журнал заказа: комментарии пользователей и записи других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, «Журнал»).

`quality` и `supply` пишут сюда синхронным вызовом фасада внутри своей транзакции —
одна транзакция БД, И4 соблюдён."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from src.production.exceptions import OperationMismatch, TextRequired
from src.production.models import JournalKind, Operation, ProductionOrder
from src.production.services.common import journal


def add_journal_entry(
    order_id: UUID,
    kind: JournalKind,
    text: str,
    *,
    operation_id: UUID | None = None,
    author_employee_id: UUID | None = None,
) -> UUID:
    text = text.strip()
    if not text:
        raise TextRequired
    with transaction.atomic():
        order = ProductionOrder.objects.get(id=order_id)
        operation = None
        if operation_id is not None:
            operation = Operation.objects.filter(id=operation_id, order=order).first()
            if operation is None:
                raise OperationMismatch
        entry = journal(
            order, JournalKind(kind), text, operation=operation, author_id=author_employee_id
        )
    return entry.id


def add_comment(
    order_id: UUID, text: str, *, operation_id: UUID | None, author_employee_id: UUID
) -> UUID:
    return add_journal_entry(
        order_id,
        JournalKind.COMMENT,
        text,
        operation_id=operation_id,
        author_employee_id=author_employee_id,
    )
