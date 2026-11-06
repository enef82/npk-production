"""Регистрация шаблонов генерации (`services/templates.register_generation_template`)."""

from __future__ import annotations

import pytest

from src.core.documents.models import DocumentTemplate, DocumentType
from src.core.documents.services.templates import register_generation_template

CODE = "test_generation_template"
DOC_TYPE_CODE = "test_generation_doc_type"


def _register(content: bytes) -> DocumentTemplate:
    return register_generation_template(
        template_code=CODE,
        template_name="Тестовый шаблон",
        doc_type_code=DOC_TYPE_CODE,
        doc_type_name="Тестовый тип",
        content=content,
        filename="template.docx",
        expected_context={"name": "имя"},
    )


@pytest.mark.django_db
def test_идемпотентна_не_плодит_типы_и_шаблоны() -> None:
    _register(b"template-bytes-v1")
    _register(b"template-bytes-v1")

    assert DocumentType.objects.filter(code=DOC_TYPE_CODE).count() == 1
    assert DocumentTemplate.objects.filter(code=CODE).count() == 1

    template = DocumentTemplate.objects.get(code=CODE)
    with template.file.open("rb") as handle:
        assert handle.read() == b"template-bytes-v1"


@pytest.mark.django_db
def test_переливает_файл_только_при_изменении_содержимого() -> None:
    template = _register(b"template-bytes-v1")
    first_name = template.file.name

    same = _register(b"template-bytes-v1")
    assert same.file.name == first_name

    changed = _register(b"template-bytes-v2")
    assert changed.file.name != first_name
    with changed.file.open("rb") as handle:
        assert handle.read() == b"template-bytes-v2"
