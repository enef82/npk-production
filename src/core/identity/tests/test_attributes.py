import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from src.core.common.exceptions import ValidationError
from src.core.identity.services.attributes import validate_against_schema
from src.core.identity.tests.factories import AttributeSchemaFactory

REQUIRES_NON_NEGATIVE_DAYS = {
    "type": "object",
    "properties": {"payment_terms_days": {"type": "integer", "minimum": 0}},
    "required": ["payment_terms_days"],
}


def test_атрибуты_без_схемы_принимаются(db: None) -> None:
    validate_against_schema({"что_угодно": 1}, "нет_такого_модуля", "нет_такой_категории")


@pytest.mark.django_db
def test_атрибуты_валидируются_по_схеме() -> None:
    AttributeSchemaFactory(
        app_label="procurement", category="vendorprofile", schema=REQUIRES_NON_NEGATIVE_DAYS
    )

    with pytest.raises(ValidationError) as excinfo:
        validate_against_schema({"payment_terms_days": -1}, "procurement", "vendorprofile")

    assert "payment_terms_days" in excinfo.value.message


@pytest.mark.django_db
def test_схема_с_синтаксической_ошибкой_не_сохраняется() -> None:
    схема = AttributeSchemaFactory.build(
        app_label="procurement", category="vendorprofile", schema={"type": "not-a-real-type"}
    )

    with pytest.raises(DjangoValidationError):
        схема.full_clean()
