"""Проверка И4: событие пишется в той же транзакции, что и изменение состояния.

`django.contrib.auth.models.Group` используется как нейтральный пример «какого-то
изменения состояния» — модуль «Ядро: события» не должен зависеть ни от одного
прикладного модуля, поэтому реального доменного события здесь нет и не нужно
(см. `tests/support.py`). `auth.User` для этой роли больше не годится: с тех пор как
`AUTH_USER_MODEL` указывает на `core_accounts.User`, стандартная модель `auth.User`
считается Django «swapped», и её менеджер `.objects` недоступен.

Тесты используют `django_db(transaction=True)`, а не обычный `django_db`: по умолчанию
pytest-django сам оборачивает тест в `transaction.atomic()` для отката после теста, и
`transaction.get_connection().in_atomic_block` был бы истинным всегда, даже без явного
`with transaction.atomic()` в теле теста. Это скрыло бы именно то, что здесь проверяется.

Откат такого теста идёт через `flush` (полная очистка таблиц), а не через rollback —
это стирает и данные, посеянные `RunPython`-миграциями (например, статьи затрат
`core.costing`), причём `serialized_rollback` эту проблему не решает: он восстанавливает
состояние ПЕРЕД следующим transactional-тестом, а не после последнего в сессии — сессия
может закончиться сразу после `flush`, оставив `--reuse-db`-базу (`pyproject.toml`)
промытой для следующего запуска `pytest`. Инвариант «ни один тест не зависит от того,
что осталось в БД от предыдущего прогона» обеспечен иначе — автоиспользуемой фикстурой
`tests/conftest.py::_ensure_core_reference_data`, а не флагом на этом маркере."""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.db import transaction

from src.core.events.models import OutboxEvent
from src.core.events.publisher import PublishOutsideTransactionError, publish
from src.core.events.tests.support import WidgetTouched


@pytest.mark.django_db(transaction=True)
def test_событие_пишется_в_одной_транзакции_с_изменением() -> None:
    aggregate_id = uuid4()

    with transaction.atomic():
        Group.objects.create(name="commit-test")
        publish(WidgetTouched(aggregate_id=aggregate_id, note="ok"))

    assert Group.objects.filter(name="commit-test").exists()
    assert OutboxEvent.objects.filter(aggregate_id=aggregate_id).exists()


@pytest.mark.django_db(transaction=True)
def test_откат_транзакции_откатывает_событие() -> None:
    aggregate_id = uuid4()

    with pytest.raises(RuntimeError), transaction.atomic():
        Group.objects.create(name="rollback-test")
        publish(WidgetTouched(aggregate_id=aggregate_id, note="boom"))
        raise RuntimeError("симуляция сбоя после publish")

    assert not Group.objects.filter(name="rollback-test").exists()
    assert not OutboxEvent.objects.filter(aggregate_id=aggregate_id).exists()


@pytest.mark.django_db(transaction=True)
def test_publish_вне_транзакции_поднимает_ошибку() -> None:
    with pytest.raises(PublishOutsideTransactionError):
        publish(WidgetTouched(aggregate_id=uuid4()))

    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_publish_сохраняет_тип_версию_и_payload() -> None:
    aggregate_id = uuid4()

    with transaction.atomic():
        publish(WidgetTouched(aggregate_id=aggregate_id, note="привет"))

    event = OutboxEvent.objects.get(aggregate_id=aggregate_id)
    assert event.event_type == WidgetTouched.event_type
    assert event.version == WidgetTouched.version
    assert event.payload == {"note": "привет"}
    assert event.processed_at is None
    assert event.attempts == 0
