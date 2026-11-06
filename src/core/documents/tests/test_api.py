"""API целиком: multipart-загрузка и список документов сущности через HTTP, а не сервис напрямую."""

from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from src.core.accounts.tests.factories import UserFactory
from src.core.documents.tests.factories import DocumentTypeFactory


@pytest.mark.django_db
def test_загрузка_и_привязка_через_api_за_один_запрос(client: Client) -> None:
    user = UserFactory()
    doc_type = DocumentTypeFactory(allowed_mime_types=["application/pdf"], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    entity_id = uuid4()
    client.force_login(user)  # type: ignore[arg-type]

    response = client.post(
        "/api/v1/documents/upload",
        {
            "file": SimpleUploadedFile("report.pdf", b"api test", content_type="application/pdf"),
            "doc_type_code": doc_type_code,
            "entity_type": "contracts.contract",
            "entity_id": str(entity_id),
            "role": "scan",
        },
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["original_name"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["version"] == 1

    list_response = client.get(f"/api/v1/documents/entity/contracts.contract/{entity_id}")
    assert list_response.status_code == 200
    documents = list_response.json()
    assert len(documents) == 1
    assert documents[0]["id"] == body["id"]


@pytest.mark.django_db
def test_список_документов_сущности_пуст_если_ничего_не_привязано(client: Client) -> None:
    user = UserFactory()
    client.force_login(user)  # type: ignore[arg-type]

    response = client.get(f"/api/v1/documents/entity/contracts.contract/{uuid4()}")

    assert response.status_code == 200
    assert response.json() == []


def test_загрузка_без_аутентификации_отклоняется(client: Client) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        {
            "file": SimpleUploadedFile("report.pdf", b"api test", content_type="application/pdf"),
            "doc_type_code": "any",
        },
    )

    assert response.status_code == 401
