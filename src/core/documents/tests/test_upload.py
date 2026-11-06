"""Загрузка: сохранение в MinIO, проверка типа/размера, контрольная сумма."""

import hashlib
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from src.core.common.exceptions import ValidationError
from src.core.documents.services.upload import DocumentUploadDTO, upload_document
from src.core.documents.tests.factories import DocumentTypeFactory

CONTENT = b"content for upload test %s" % uuid4().hex.encode()


@pytest.mark.django_db
def test_файл_загружается_в_хранилище_и_читается_обратно() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=["application/pdf"], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("report.pdf", CONTENT, content_type="application/pdf")

    document = upload_document(
        DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
    )

    with document.file.open("rb") as stored:
        assert stored.read() == CONTENT


@pytest.mark.django_db
def test_контрольная_сумма_совпадает_после_загрузки() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=["application/pdf"], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("report.pdf", CONTENT, content_type="application/pdf")

    document = upload_document(
        DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
    )

    assert document.checksum == hashlib.sha256(CONTENT).hexdigest()
    with document.file.open("rb") as stored:
        assert hashlib.sha256(stored.read()).hexdigest() == document.checksum


@pytest.mark.django_db
def test_файл_недопустимого_типа_отклоняется() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=["application/pdf"], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("image.png", b"not a pdf", content_type="image/png")

    with pytest.raises(ValidationError):
        upload_document(
            DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
        )


@pytest.mark.django_db
def test_превышение_размера_отклоняется() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=["application/pdf"], max_size_bytes=10)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("report.pdf", CONTENT, content_type="application/pdf")

    with pytest.raises(ValidationError):
        upload_document(
            DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
        )


@pytest.mark.django_db
def test_отказ_по_размеру_называет_лимит_и_фактический_размер() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=[], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("komplekt.pdf", b"x" * 5000, content_type="application/pdf")

    with pytest.raises(ValidationError) as exc:
        upload_document(
            DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
        )

    assert "МБ" in str(exc.value)
    assert "лимит" in str(exc.value).lower()


@pytest.mark.django_db
def test_пустой_список_mime_разрешает_любой_тип() -> None:
    """Регрессия на типовую ловушку: пустой `allowed_mime_types` — «любой», не «никакой»."""

    doc_type = DocumentTypeFactory(allowed_mime_types=[], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("shema.dwg", b"binary dwg", content_type="image/vnd.dwg")

    document = upload_document(
        DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
    )

    assert document.original_name == "shema.dwg"


@pytest.mark.django_db
def test_исполняемый_файл_отклоняется_при_пустом_списке_mime() -> None:
    doc_type = DocumentTypeFactory(allowed_mime_types=[], max_size_bytes=1024)
    doc_type_code: str = doc_type.code  # type: ignore[assignment]
    file = SimpleUploadedFile("setup.exe", b"MZ", content_type="application/x-msdownload")

    with pytest.raises(ValidationError):
        upload_document(
            DocumentUploadDTO(file=file, doc_type_code=doc_type_code, uploaded_by=uuid4())
        )
