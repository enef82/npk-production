"""Валидация JSONB-атрибутов профилей по зарегистрированным JSON Schema."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaError
from jsonschema.exceptions import best_match
from referencing import Registry

from src.core.common.exceptions import ValidationError
from src.core.identity.models import AttributeSchema

# Без retrieve-коллбэка Registry никогда не уходит в сеть за внешними $ref —
# схемы редактируются через админку, и разрешение произвольного $ref по HTTP
# было бы SSRF.
_NO_NETWORK_REGISTRY: Registry[Any] = Registry()


def _describe_enum(error: JSONSchemaError) -> str:
    values = list(cast(Iterable[Any], error.validator_value))
    return f"значение {error.instance!r} не входит в список допустимых {values!r}"


_MESSAGES: dict[str, Callable[[JSONSchemaError], str]] = {
    "required": lambda e: "обязательно к заполнению",
    "type": lambda e: f"ожидался тип «{e.validator_value}», передано значение {e.instance!r}",
    "enum": _describe_enum,
    "minimum": lambda e: f"значение {e.instance!r} меньше минимума {e.validator_value!r}",
    "maximum": lambda e: f"значение {e.instance!r} больше максимума {e.validator_value!r}",
    "pattern": lambda e: f"значение {e.instance!r} не соответствует шаблону «{e.validator_value}»",
}


def _field_name(error: JSONSchemaError) -> str:
    if error.validator == "required":
        present = set(error.instance) if isinstance(error.instance, dict) else set()
        missing = set(cast(Iterable[Any], error.validator_value)) - present
        return ", ".join(sorted(missing)) or "attributes"
    if error.path:
        return ".".join(str(part) for part in error.path)
    return "attributes"


def _format_error(error: JSONSchemaError) -> str:
    describe = _MESSAGES.get(str(error.validator))
    reason = describe(error) if describe else error.message
    return f"Поле «{_field_name(error)}»: {reason}"


def validate_against_schema(attributes: dict[str, Any], app_label: str, category: str) -> None:
    """Ничего не делает, если для (app_label, category) схема не зарегистрирована."""

    schema_record = AttributeSchema.objects.filter(
        app_label=app_label, category=category, is_active=True
    ).first()
    if schema_record is None:
        return

    validator = Draft202012Validator(schema_record.schema, registry=_NO_NETWORK_REGISTRY)
    error = best_match(validator.iter_errors(attributes))
    if error is None:
        return

    raise ValidationError(_format_error(error))
