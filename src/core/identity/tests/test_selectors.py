"""`get_parties_brief` — пакетное чтение контрагентов, один запрос независимо от
количества id (первый потребитель — реестр заявок `crm`, `crm.api.routers`)."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from src.core.identity.selectors import get_parties_brief
from src.core.identity.tests.factories import PartyFactory


@pytest.mark.django_db
def test_get_parties_brief_делает_один_запрос_независимо_от_количества_id() -> None:
    parties = [PartyFactory() for _ in range(5)]
    ids = [party.id for party in parties]  # type: ignore[attr-defined]

    with CaptureQueriesContext(connection) as ctx:
        briefs = get_parties_brief(ids)

    assert len(ctx.captured_queries) == 1
    assert set(briefs.keys()) == set(ids)
    assert briefs[ids[0]].short_name == parties[0].short_name  # type: ignore[comparison-overlap]


@pytest.mark.django_db
def test_get_parties_brief_с_пустым_списком_не_делает_запрос() -> None:
    with CaptureQueriesContext(connection) as ctx:
        briefs = get_parties_brief([])

    assert briefs == {}
    assert len(ctx.captured_queries) == 0
