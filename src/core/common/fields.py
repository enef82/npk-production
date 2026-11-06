from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.expressions import Combinable

if TYPE_CHECKING:
    # Базу оставляем непараметризованной (`Any, Any`) намеренно: конкретные параметры
    # (`DecimalField[str | Decimal | Combinable, Decimal]`) лишают mypy_django_plugin
    # возможности навесить `| None` на get-тип по `null=True` — он подставляет параметр
    # базы как есть. С `Any` плагин берёт тип из `_pyi_private_*_type` (ниже) и сам
    # делает его optional для nullable-полей. Итог: `MoneyField()` читается как `Decimal`,
    # `MoneyField(null=True)` — как `Decimal | None`, без `type: ignore` на месте.
    _MoneyFieldBase = models.DecimalField[Any, Any]
else:
    _MoneyFieldBase = models.DecimalField


class MoneyField(_MoneyFieldBase):
    """DecimalField для денег и количеств: max_digits=18, decimal_places=4, float запрещён.

    Поддерживает `null=True` (пример — `crm.Quotation.contingency_amount`): у таких
    полей get-тип — `Decimal | None`.
    """

    if TYPE_CHECKING:
        # set-тип без `float` — присваивание float отклоняется и на уровне типов (И6),
        # не только рантайм-проверкой `_reject_float` ниже. `get`/`lookup` — как у
        # `DecimalField`, чтобы `.filter(amount=...)` принимал строку/int по-прежнему.
        _pyi_private_set_type: Decimal | str | Combinable
        _pyi_private_get_type: Decimal
        _pyi_lookup_exact_type: str | int | Decimal

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 18)
        kwargs.setdefault("decimal_places", 4)
        kwargs.setdefault("verbose_name", "Сумма")
        super().__init__(*args, **kwargs)

    def _reject_float(self, value: Any) -> None:
        if isinstance(value, float):
            raise ValidationError(
                "Денежные значения должны быть Decimal, а не float.",
                code="invalid_money_type",
            )

    def to_python(self, value: Any) -> Any:
        self._reject_float(value)
        return super().to_python(value)

    def get_prep_value(self, value: Any) -> Any:
        self._reject_float(value)
        return super().get_prep_value(value)
