"""Генерация DOCX из шаблона (docxtpl) и конвертация в PDF (Gotenberg, замокан — внешний HTTP)."""

from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document as WordDocument

from src.core.documents.models import Document, DocumentType
from src.core.documents.services.generation import (
    DOCX_MIME_TYPE,
    render_docx_from_template,
    render_template_to_docx,
    render_to_pdf,
    store_generated_document,
)
from src.core.documents.tests.factories import (
    DocumentTemplateFactory,
    DocumentTypeFactory,
    build_docx_bytes,
)


@pytest.mark.django_db
def test_генерация_docx_из_шаблона_подставляет_контекст() -> None:
    template = DocumentTemplateFactory(
        file=SimpleUploadedFile(
            "template.docx",
            build_docx_bytes("Здравствуйте, {{ name }}!"),
            content_type=DOCX_MIME_TYPE,
        )
    )

    template_id = template.id  # type: ignore[attr-defined]
    template_doc_type_id = template.doc_type_id  # type: ignore[attr-defined]

    document = render_docx_from_template(template_id, {"name": "Иван"}, actor_id=uuid4())

    with document.file.open("rb") as rendered:
        rendered_docx = WordDocument(rendered)
        text = "\n".join(p.text for p in rendered_docx.paragraphs)

    assert "Здравствуйте, Иван!" in text
    assert document.doc_type_id == template_doc_type_id


@pytest.mark.django_db
def test_render_template_to_docx_возвращает_байты_и_не_пишет_в_бд() -> None:
    template = DocumentTemplateFactory(
        file=SimpleUploadedFile(
            "template.docx",
            build_docx_bytes("Объект: {{ object }}"),
            content_type=DOCX_MIME_TYPE,
        )
    )
    before = Document.objects.count()

    content = render_template_to_docx(template.id, {"object": "Иркутская ТЭЦ"})  # type: ignore[attr-defined]

    assert Document.objects.count() == before
    word = WordDocument(BytesIO(content))
    assert "Объект: Иркутская ТЭЦ" in "\n".join(p.text for p in word.paragraphs)


@pytest.mark.django_db
def test_store_generated_document_версионирует_через_supersedes() -> None:
    doc_type: DocumentType = DocumentTypeFactory()  # type: ignore[assignment]
    first = store_generated_document(
        b"one",
        original_name="doc.docx",
        mime_type=DOCX_MIME_TYPE,
        doc_type=doc_type,
        actor_id=uuid4(),
    )
    second = store_generated_document(
        b"two",
        original_name="doc.docx",
        mime_type=DOCX_MIME_TYPE,
        doc_type=doc_type,
        actor_id=uuid4(),
        supersedes=first,
    )

    assert first.version == 1
    assert second.version == 2
    assert second.supersedes_id == first.id


def test_render_to_pdf_вызывает_gotenberg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Юнит-тест на форму запроса (эндпоинт, поле files) — HTTP замокан намеренно.

    Он не доказывает, что Gotenberg действительно принимает такой запрос и отдаёт PDF —
    для этого есть test_render_to_pdf_конвертирует_реальный_docx_через_gotenberg ниже.
    """

    fake_response = Mock(spec=httpx.Response)
    fake_response.content = b"%PDF-1.4 fake pdf"
    fake_response.raise_for_status = Mock()
    post_mock = Mock(return_value=fake_response)
    monkeypatch.setattr("src.core.documents.services.generation.httpx.post", post_mock)

    result = render_to_pdf(b"docx bytes", filename="doc.docx")

    assert result == b"%PDF-1.4 fake pdf"
    post_mock.assert_called_once()
    called_url = post_mock.call_args.args[0]
    assert called_url.endswith("/forms/libreoffice/convert")


@pytest.mark.integration
def test_render_to_pdf_конвертирует_реальный_docx_через_gotenberg() -> None:
    """Настоящий вызов Gotenberg (docker compose up gotenberg), без моков.

    Проверяет ровно то, что мок не может проверить: правильный эндпоинт, имя поля в
    multipart, content-type и то, что Gotenberg реально отдаёт PDF на такой запрос —
    иначе поломка API/образа Gotenberg вскроется не в CI, а на первом реальном документе.
    """

    docx_bytes = build_docx_bytes("Здравствуйте, {{ name }}!")

    result = render_to_pdf(docx_bytes, filename="smoke.docx")

    assert result.startswith(b"%PDF-")
