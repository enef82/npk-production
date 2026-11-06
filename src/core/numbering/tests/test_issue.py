"""Атомарная выдача номера: конкурентность, сброс по периоду, независимость юрлиц."""

import threading
from datetime import date

import pytest
from django.db import connection

from src.core.numbering.models import NumeratorResetPeriod
from src.core.numbering.services import issue_number
from src.core.numbering.tests.factories import NumeratorFactory
from src.core.org.tests.factories import LegalEntityFactory


@pytest.mark.django_db(transaction=True)
def test_конкурентная_выдача_номеров_не_даёт_дублей() -> None:
    код = "test.concurrent"
    NumeratorFactory(code=код)

    numbers: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            number = issue_number(код)
            with lock:
                numbers.append(number)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(numbers) == 50
    assert len(set(numbers)) == 50


@pytest.mark.django_db
def test_нумератор_сбрасывается_в_новом_году() -> None:
    код = "test.yearly"
    NumeratorFactory(
        code=код, reset_period=NumeratorResetPeriod.YEARLY, template="ДГ-{year}-{seq:03d}"
    )

    first = issue_number(код, when=date(2025, 12, 31))
    second = issue_number(код, when=date(2025, 12, 31))
    third = issue_number(код, when=date(2026, 1, 1))

    assert first == "ДГ-2025-001"
    assert second == "ДГ-2025-002"
    assert third == "ДГ-2026-001"


@pytest.mark.django_db
def test_нумератор_сбрасывается_в_новом_месяце() -> None:
    код = "test.monthly"
    NumeratorFactory(
        code=код, reset_period=NumeratorResetPeriod.MONTHLY, template="{year}{month:02d}-{seq:03d}"
    )

    first = issue_number(код, when=date(2026, 8, 31))
    second = issue_number(код, when=date(2026, 9, 1))

    assert first == "202608-001"
    assert second == "202609-001"


@pytest.mark.django_db
def test_нумератор_без_сброса_продолжает_счёт_через_границу_года() -> None:
    код = "test.never"
    NumeratorFactory(code=код, reset_period=NumeratorResetPeriod.NEVER, template="{seq:03d}")

    first = issue_number(код, when=date(2025, 12, 31))
    second = issue_number(код, when=date(2026, 1, 1))

    assert first == "001"
    assert second == "002"


@pytest.mark.django_db
def test_нумераторы_разных_юрлиц_независимы() -> None:
    первое_юрлицо = LegalEntityFactory()
    второе_юрлицо = LegalEntityFactory()
    первый_код = "test.le1"
    второй_код = "test.le2"
    NumeratorFactory(code=первый_код, legal_entity=первое_юрлицо, template="{seq:03d}")
    NumeratorFactory(code=второй_код, legal_entity=второе_юрлицо, template="{seq:03d}")

    issue_number(первый_код)
    issue_number(первый_код)
    единственный_у_второго = issue_number(второй_код)

    assert единственный_у_второго == "001"
