"""Celery-задачи модуля «Ядро: документы»: только оркестрация, логика — в services."""

from __future__ import annotations

from celery import shared_task

from src.core.documents.services.maintenance import sweep_orphaned_storage_objects


@shared_task(name="core_documents.sweep_orphaned_storage_objects")  # type: ignore[untyped-decorator]
def sweep_orphaned_storage_objects_task() -> int:
    """Ежедневная уборка объектов бакета без ссылающегося `Document` (спец. CRM ИС
    §3.10, §9). Файл вложения пишется в хранилище до транзакции — откат оставляет объект,
    который убирать здесь."""

    return sweep_orphaned_storage_objects()
