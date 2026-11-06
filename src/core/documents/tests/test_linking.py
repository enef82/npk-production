"""Привязка документа к произвольной сущности через (entity_type, entity_id) — без contenttypes."""

from uuid import uuid4

import pytest

from src.core.documents.models import Document, DocumentLink
from src.core.documents.services.linking import attach_document, detach_document
from src.core.documents.tests.factories import DocumentFactory


@pytest.mark.django_db
def test_документ_привязывается_к_любой_сущности_без_contenttypes() -> None:
    document = DocumentFactory()
    document_id = document.id  # type: ignore[attr-defined]
    entity_id = uuid4()

    link = attach_document(document_id, "contracts.contract", entity_id, role="scan")

    assert link.entity_type == "contracts.contract"
    assert link.entity_id == entity_id
    assert link.role == "scan"
    # DocumentLink не ссылается ни на одну модель функционального модуля — только строки/UUID.
    # Только прямые поля (`concrete`): core.audit добавляет DocumentLinkEvent.pgh_obj — это
    # обратная связь от собственной таблицы истории DocumentLink, а не исходящая ссылка.
    model_fields = DocumentLink._meta.get_fields()
    assert {f.related_model for f in model_fields if f.is_relation and f.concrete} == {Document}


@pytest.mark.django_db
def test_отвязка_удаляет_link_но_не_document() -> None:
    document = DocumentFactory()
    document_id = document.id  # type: ignore[attr-defined]
    entity_id = uuid4()
    attach_document(document_id, "crm.lead", entity_id)

    detach_document(document_id, "crm.lead", entity_id)

    assert not DocumentLink.objects.filter(document_id=document_id, entity_type="crm.lead").exists()


@pytest.mark.django_db
def test_одна_и_та_же_привязка_идемпотентна() -> None:
    document = DocumentFactory()
    document_id = document.id  # type: ignore[attr-defined]
    entity_id = uuid4()

    attach_document(document_id, "crm.lead", entity_id, role="скан")
    attach_document(document_id, "crm.lead", entity_id, role="скан")

    assert DocumentLink.objects.filter(document_id=document_id, entity_type="crm.lead").count() == 1
