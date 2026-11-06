"""Новая версия документа не затирает предыдущую."""

from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from src.core.documents.selectors import get_current_version
from src.core.documents.services.linking import attach_document
from src.core.documents.services.versioning import upload_new_version
from src.core.documents.tests.factories import DocumentFactory

OLD_CONTENT = b"old version content"
NEW_CONTENT = b"new version content"


@pytest.mark.django_db
def test_новая_версия_не_затирает_предыдущую() -> None:
    original = DocumentFactory(
        file=SimpleUploadedFile("scan.pdf", OLD_CONTENT, content_type="application/pdf")
    )
    original_id = original.id  # type: ignore[attr-defined]
    original_version = original.version  # type: ignore[attr-defined]
    new_file = SimpleUploadedFile("scan.pdf", NEW_CONTENT, content_type="application/pdf")

    new_version = upload_new_version(original_id, new_file, actor_id=uuid4())

    assert new_version.version == original_version + 1
    assert new_version.supersedes_id == original_id

    original.refresh_from_db()  # type: ignore[attr-defined]
    with original.file.open("rb") as stored:  # type: ignore[attr-defined]
        assert stored.read() == OLD_CONTENT
    with new_version.file.open("rb") as stored:
        assert stored.read() == NEW_CONTENT


@pytest.mark.django_db
def test_get_current_version_возвращает_последнюю() -> None:
    original = DocumentFactory()
    original_id = original.id  # type: ignore[attr-defined]
    entity_id = uuid4()
    attach_document(original_id, "contracts.contract", entity_id, role="original")

    new_file = SimpleUploadedFile("scan.pdf", NEW_CONTENT, content_type="application/pdf")
    new_version = upload_new_version(original_id, new_file, actor_id=uuid4())

    current = get_current_version("contracts.contract", entity_id, role="original")

    assert current is not None
    assert current.id == new_version.id
