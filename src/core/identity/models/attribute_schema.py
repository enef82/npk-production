from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class AttributeSchema(UUIDPrimaryKeyModel, TimeStampedModel):
    """JSON Schema, привязанная к паре (модуль, категория) — валидирует attributes профилей."""

    app_label = models.CharField("Модуль", max_length=64)
    category = models.CharField("Категория", max_length=64)
    schema = models.JSONField("JSON Schema")
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Схема атрибутов"
        verbose_name_plural = "Схемы атрибутов"
        constraints = [
            models.UniqueConstraint(
                fields=["app_label", "category"],
                name="core_identity_attributeschema_uniq_app_label_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.app_label}.{self.category}"

    def clean(self) -> None:
        try:
            Draft202012Validator.check_schema(self.schema)
        except SchemaError as exc:
            raise DjangoValidationError({"schema": f"Схема некорректна: {exc.message}"}) from exc
