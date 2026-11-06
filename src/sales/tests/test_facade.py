"""Фасад «Заявок» для портфеля: вероятности этапов из настроек."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.sales import facade
from src.sales.models import InquiryStage, SalesSettings

pytestmark = pytest.mark.django_db


def test_вероятности_этапов_по_умолчанию_и_из_настроек() -> None:
    SalesSettings.objects.all().delete()
    assert facade.get_stage_probabilities() == {
        InquiryStage.NEW: Decimal("10"),
        InquiryStage.CALC: Decimal("30"),
        InquiryStage.APPROVAL: Decimal("60"),
    }

    SalesSettings.objects.create(
        prob_new=Decimal("5"), prob_calc=Decimal("25"), prob_approval=Decimal("70")
    )

    assert facade.get_stage_probabilities()[InquiryStage.APPROVAL] == Decimal("70")
