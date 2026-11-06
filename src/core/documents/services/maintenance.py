"""Регламентная уборка осиротевших объектов в бакете.

Файл вложения пишется в хранилище **до** транзакции, создающей `Document`
(`services/upload.store_upload`, спец. CRM ИС §3.10). Если та транзакция
откатится, объект останется в бакете без строки `Document` — «осиротеет». Тот же
класс мусора породит и прямая загрузка по предподписанной ссылке, когда её добавят,
поэтому уборка одна на оба случая.

Удаляется объект, у которого одновременно: (1) в ключе `documents/<id>/<file>` нет
строки `Document` с таким `id`, и (2) он старше `grace_hours`.

Отступ `grace_hours` — не «на всякий случай», а защита от гонки: файл пишется в
хранилище **до** транзакции, и между записью объекта и коммитом создающей его строки
`Document` объект секунды-минуты выглядит осиротевшим, хотя транзакция ещё идёт.
Регламентная задача (`tasks.sweep_orphaned_storage_objects_task`) зовёт эту функцию с
дефолтным суточным отступом; ноль допустим только в тестах, где гонки нет.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import UUID

from django.core.files.storage import default_storage
from django.utils import timezone
from storages.backends.s3 import S3Storage

from src.core.documents.models import Document

_PREFIX = "documents/"


def _document_id_from_key(key: str) -> UUID | None:
    parts = key.split("/")
    if len(parts) < 3 or parts[0] != "documents":
        return None
    try:
        return UUID(parts[1])
    except ValueError:
        return None


def sweep_orphaned_storage_objects(*, grace_hours: int = 24) -> int:
    """Удаляет из бакета объекты под `documents/`, на которые нет `Document` и которые
    старше `grace_hours`. Возвращает число удалённых объектов."""

    storage = cast(S3Storage, default_storage)
    cutoff = timezone.now() - timedelta(hours=grace_hours)

    candidates: dict[str, UUID] = {}
    for summary in storage.bucket.objects.filter(Prefix=_PREFIX):
        if summary.last_modified > cutoff:
            continue
        document_id = _document_id_from_key(summary.key)
        if document_id is not None:
            candidates[summary.key] = document_id

    if not candidates:
        return 0

    alive = set(
        Document.objects.filter(id__in=set(candidates.values())).values_list("id", flat=True)
    )
    orphan_keys = [key for key, doc_id in candidates.items() if doc_id not in alive]

    for key in orphan_keys:
        storage.delete(key)

    return len(orphan_keys)
