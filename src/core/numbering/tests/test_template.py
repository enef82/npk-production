"""Валидация формат-строки шаблона номера — опечатка ловится при сохранении, не при
выпуске первого документа."""

import pytest

from src.core.common.exceptions import ValidationError
from src.core.numbering.template import validate_numerator_template


def test_шаблон_с_известными_подстановками_проходит() -> None:
    validate_numerator_template("ДГ-{year}-{seq:05d}")


def test_шаблон_без_seq_отклоняется() -> None:
    with pytest.raises(ValidationError):
        validate_numerator_template("ДГ-{year}")


def test_шаблон_с_неизвестной_подстановкой_отклоняется() -> None:
    with pytest.raises(ValidationError):
        validate_numerator_template("{unknown}-{seq}")


def test_шаблон_с_позиционной_подстановкой_отклоняется() -> None:
    with pytest.raises(ValidationError):
        validate_numerator_template("{}-{seq}")
