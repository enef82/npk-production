import hashlib
from io import BytesIO
from uuid import uuid4

import factory
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document as WordDocument

from src.core.documents.models import Document, DocumentTemplate, DocumentType

PDF_CONTENT = b"%PDF-1.4 test content for core.documents tests"


def build_docx_bytes(paragraph_text: str = "Здравствуйте, {{ name }}!") -> bytes:
    """Минимальный валидный .docx с одним абзацем-плейсхолдером для docxtpl."""

    word_document = WordDocument()
    word_document.add_paragraph(paragraph_text)
    buffer = BytesIO()
    word_document.save(buffer)
    return buffer.getvalue()


class DocumentTypeFactory(factory.django.DjangoModelFactory[DocumentType]):
    class Meta:
        model = DocumentType

    code = factory.Sequence(lambda n: f"doc-type-{n}")
    name = factory.Sequence(lambda n: f"Тип документа {n}")
    allowed_mime_types = factory.LazyFunction(lambda: ["application/pdf"])
    max_size_bytes = 10 * 1024 * 1024
    requires_approval = False
    is_active = True


class DocumentFactory(factory.django.DjangoModelFactory[Document]):
    class Meta:
        model = Document

    original_name = "scan.pdf"
    file = factory.LazyFunction(
        lambda: SimpleUploadedFile("scan.pdf", PDF_CONTENT, content_type="application/pdf")
    )
    size_bytes = len(PDF_CONTENT)
    mime_type = "application/pdf"
    checksum = factory.LazyFunction(lambda: hashlib.sha256(PDF_CONTENT).hexdigest())
    doc_type = factory.SubFactory(DocumentTypeFactory)
    uploaded_by = factory.LazyFunction(uuid4)


class DocumentTemplateFactory(factory.django.DjangoModelFactory[DocumentTemplate]):
    class Meta:
        model = DocumentTemplate

    code = factory.Sequence(lambda n: f"tpl-{n}")
    name = factory.Sequence(lambda n: f"Шаблон {n}")
    doc_type = factory.SubFactory(DocumentTypeFactory)
    file = factory.LazyFunction(
        lambda: SimpleUploadedFile(
            "template.docx",
            build_docx_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )
    expected_context = factory.LazyFunction(lambda: {"name": "имя получателя"})
    is_active = True
