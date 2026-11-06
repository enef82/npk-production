"""Доменные исключения модуля «Энергоучёт» (подклассы `DomainError`: 400/409, не 500)."""

from __future__ import annotations

from src.core.common.exceptions import ConflictError, ValidationError


class MeterCodeTaken(ConflictError):
    code = "meter_code_taken"
    default_message = "Счётчик с таким кодом уже есть."


class InvalidParent(ValidationError):
    code = "invalid_parent"
    default_message = "Родитель — счётчик того же ресурса, и дерево не может замкнуться в цикл."


class InvalidTariff(ValidationError):
    code = "invalid_tariff"
    default_message = "Тариф не может быть отрицательным."


class InvalidReading(ValidationError):
    code = "invalid_reading"
    default_message = "Показание не принято."


class UnsupportedSchemaVersion(ValidationError):
    code = "unsupported_schema_version"
    default_message = "Версия формата пакета не поддерживается."
