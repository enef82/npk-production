from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import isolate_apps

from src.core.common.fields import MoneyField
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@pytest.mark.django_db
@isolate_apps()
def test_moneyfield_сохраняет_и_читает_точное_значение() -> None:
    class MoneyFieldFixture(UUIDPrimaryKeyModel, TimeStampedModel):
        amount = MoneyField()

        class Meta:
            app_label = "common"

    with connection.schema_editor() as editor:
        editor.create_model(MoneyFieldFixture)
    try:
        MoneyFieldFixture.objects.create(amount=Decimal("1234.5678"))  # type: ignore[attr-defined]
        stored = MoneyFieldFixture.objects.get().amount  # type: ignore[attr-defined]

        assert stored == Decimal("1234.5678")
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(MoneyFieldFixture)


def test_moneyfield_не_принимает_float() -> None:
    field = MoneyField()

    with pytest.raises(ValidationError):
        field.get_prep_value(1234.5678)
