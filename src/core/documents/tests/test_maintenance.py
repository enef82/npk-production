"""Регламентная уборка осиротевших объектов бакета (спец. CRM ИС §3.10, §9).

Бакет теста — сессионный и общий (`conftest._test_storage_bucket`): файлы `DocumentFactory`
переживают откат транзакции каждого теста, поэтому уборка находит и чужие осиротевшие
объекты. Проверяем поведение на конкретных ключах, а не на суммарном счётчике.
"""

from __future__ import annotations

from typing import cast

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from storages.backends.s3 import S3Storage

from src.core.documents.models import Document
from src.core.documents.services.maintenance import sweep_orphaned_storage_objects
from src.core.documents.tasks import sweep_orphaned_storage_objects_task
from src.core.documents.tests.factories import DocumentFactory


@pytest.mark.django_db
def test_осиротевший_объект_убирается_а_привязанный_к_document_остаётся() -> None:
    alive = DocumentFactory()
    alive_key = alive.file.name  # type: ignore[attr-defined]

    orphan = DocumentFactory()
    orphan_key = orphan.file.name  # type: ignore[attr-defined]
    # Стираем строку Document, файл в бакете остаётся — ровно то, что делает откат
    # транзакции после записи файла до её открытия.
    Document.objects.filter(id=orphan.id).delete()  # type: ignore[attr-defined]

    removed = sweep_orphaned_storage_objects(grace_hours=0)

    assert removed >= 1
    assert default_storage.exists(alive_key)
    assert not default_storage.exists(orphan_key)


@pytest.mark.django_db
def test_свежий_осиротевший_объект_в_пределах_grace_не_трогается() -> None:
    orphan = DocumentFactory()
    orphan_key = orphan.file.name  # type: ignore[attr-defined]
    Document.objects.filter(id=orphan.id).delete()  # type: ignore[attr-defined]

    sweep_orphaned_storage_objects(grace_hours=24)

    assert default_storage.exists(orphan_key)


@pytest.mark.django_db
def test_регламентная_задача_не_трогает_только_что_записанный_объект() -> None:
    """Файл пишется до транзакции: секунду назад записанный объект без строки Document —
    это ещё не сирота, а гонка с идущей транзакцией. Задача зовётся с суточным отступом."""

    orphan = DocumentFactory()
    orphan_key = orphan.file.name  # type: ignore[attr-defined]
    Document.objects.filter(id=orphan.id).delete()  # type: ignore[attr-defined]

    sweep_orphaned_storage_objects_task()

    assert default_storage.exists(orphan_key)


@pytest.mark.django_db
def test_объект_вне_префикса_documents_не_рассматривается() -> None:
    storage = cast(S3Storage, default_storage)
    key = storage.save("other/loose-object.txt", ContentFile(b"not ours"))
    try:
        sweep_orphaned_storage_objects(grace_hours=0)
        assert default_storage.exists(key)
    finally:
        default_storage.delete(key)
