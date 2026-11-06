"""Ровно одна основная организация (partial UniqueConstraint core_org_legalentity_uniq_primary)."""

import pytest
from django.db import IntegrityError, transaction

from src.core.org.models import LegalEntity
from src.core.org.services import set_primary_legal_entity
from src.core.org.tests.factories import LegalEntityFactory


@pytest.mark.django_db
def test_нельзя_пометить_вторую_организацию_основной() -> None:
    LegalEntityFactory(is_primary=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        LegalEntityFactory(is_primary=True)


@pytest.mark.django_db
def test_можно_создать_несколько_неосновных_организаций() -> None:
    LegalEntityFactory(is_primary=False)
    LegalEntityFactory(is_primary=False)

    assert LegalEntity.objects.filter(is_primary=False).count() == 2


@pytest.mark.django_db
def test_смена_основной_организации_проходит_через_сервис() -> None:
    старая = LegalEntityFactory(is_primary=True)
    новая = LegalEntityFactory(is_primary=False)

    set_primary_legal_entity(новая.pk)  # type: ignore[attr-defined]

    старая.refresh_from_db()  # type: ignore[attr-defined]
    новая.refresh_from_db()  # type: ignore[attr-defined]
    assert старая.is_primary is False
    assert новая.is_primary is True
