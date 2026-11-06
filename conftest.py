"""Корневой `conftest.py` — обязан жить в корне репозитория, не в `tests/`:
`testpaths = ["tests", "src"]` (`pyproject.toml`) — сиблинги, не вложенные друг в друга,
и `conftest.py` внутри `tests/` не действует на тесты под `src/*/tests/` (обнаружено
на этом же дефекте — фикстура ниже сначала была в `tests/conftest.py` и молча не
применялась ни к одному тесту вне `tests/`, включая тот единственный, ради которого её
и заводили)."""

import importlib
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.storage import default_storage, storages
from django.utils.functional import empty

from src.core.documents.models import DocumentType
from src.core.numbering.models import Numerator
from src.core.org.models import Position
from tests.reference_data import (
    CORE_DOCUMENT_TYPES,
    CORE_NUMERATORS,
    CORE_TRADE_POSITIONS,
    DOCUMENT_MAX_SIZE_BYTES,
)

# Посев справочников модулей их же data-миграциями: (миграция, модель-признак). Функция
# `seed` каждой из них идемпотентна (`get_or_create`), поэтому повторный вызов после
# `flush()` восстанавливает ровно то, что дала бы миграция, без второго списка значений.
MODULE_SEED_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("src.timesheet.migrations.0002_seed_time_codes", "timesheet.TimeCode"),
    ("src.timesheet.migrations.0003_seed_repair_locked_notification", ""),
    ("src.equipment.migrations.0003_seed_reference_lists", "equipment.IdleReason"),
    ("src.energy.migrations.0002_seed_energy_resources", "energy.EnergyResource"),
)


def _restore_module_seeds() -> None:
    for module_path, sentinel in MODULE_SEED_MIGRATIONS:
        if sentinel and apps.get_model(sentinel).objects.exists():
            continue
        importlib.import_module(module_path).seed(apps, None)


def ensure_core_reference_data() -> None:
    """Ни один тест не вправе зависеть от того, что осталось в физической БД от
    предыдущего прогона `pytest` — `--reuse-db` (`pyproject.toml`) переживает процесс,
    а `TransactionTestCase.flush()` (любой `django_db(transaction=True)`-тест) стирает
    RunPython-посев без возможности восстановить его штатным `migrate` (уже применённая
    миграция повторно не выполняется). Тот же класс дефекта, что `_clean_registry` до
    шага 11 (`docs/adr/0001-shablon-modulya.md`): общее состояние, живущее дольше теста,
    обязано восстанавливаться фикстурой, а не оставаться на волю прежних прогонов —
    здесь это не Python-реестр, а таблица в БД, но принцип тот же
    (`docs/checklist-novyy-modul.md` §9). Регрессия на саму эту функцию —
    `tests/test_conftest.py`, по образцу `src/core/events/tests/test_conftest.py`.

    Списки — `tests/reference_data.py`. Без строк нумераторов сервисы создания
    документов не работают, а первый же `django_db(transaction=True)`-тест стирает их
    для всех остальных тестов на `--reuse-db`.

    `get_or_create` — идемпотентная проверка наличия, не полный reseed. Вызывается
    отдельной плоской функцией (не только из фикстуры), чтобы тест мог позвать её
    напрямую после симуляции стирания — так же, как `restore_handlers` в
    `src/core/events/tests/conftest.py`.
    """

    for name, category in CORE_TRADE_POSITIONS:
        Position.objects.get_or_create(name=name, category=category, defaults={"grade": ""})

    for code, name, template, reset_period in CORE_NUMERATORS:
        Numerator.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "template": template,
                "legal_entity": None,
                "reset_period": reset_period,
                "is_active": True,
            },
        )

    for code, name in CORE_DOCUMENT_TYPES:
        DocumentType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "allowed_mime_types": [],
                "max_size_bytes": DOCUMENT_MAX_SIZE_BYTES,
                "is_active": True,
            },
        )
    _restore_module_seeds()


@pytest.fixture(autouse=True)
def _ensure_core_reference_data(request: pytest.FixtureRequest) -> None:
    """Перед КАЖДЫМ тестом, которому разрешён доступ к БД (autouse, но не безусловно) —
    не разовый reseed сессии: разово восстановленные данные тот же `flush()` сотрёт у
    следующего transactional-теста. Цена — 11 индексных lookup'ов по `code` на такой
    тест, не заметна на фоне остальной работы теста.

    Доступ к БД запрашивается только если тест сам его запросил — та же проверка, что
    делает pytest-django внутри себя (`_get_databases_for_test`): маркер `django_db`
    либо фикстуры `db`/`transactional_db`/`live_server` среди уже собранных для теста.
    Без этой проверки фикстура запрашивала бы `db` безусловно для всех тестов и ломала
    тесты вроде `test_health_показывает_недоступность_бд`
    (`tests/test_health.py`), которые намеренно не берут доступ к БД через
    pytest-django, а подделывают его отказ через `monkeypatch` внутри теста — наш же
    `Numerator.objects.get_or_create()` в фикстуре успел бы обратиться к ещё не
    подделанному соединению до этого."""

    marker = request.node.get_closest_marker("django_db")
    fixtures = request.fixturenames
    uses_db = (
        marker is not None
        or "db" in fixtures
        or "transactional_db" in fixtures
        or "live_server" in fixtures
    )
    if not uses_db:
        return

    request.getfixturevalue("db")
    ensure_core_reference_data()


def _empty_bucket(client: Any, bucket_name: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if keys:
            client.delete_objects(Bucket=bucket_name, Delete={"Objects": keys})


@pytest.fixture(scope="session", autouse=True)
def _test_storage_bucket() -> Iterator[None]:
    """`DocumentFactory()`/`S3Storage` реально загружает файл в MinIO — это происходит
    вне транзакции Django-теста и не откатывается вместе со строкой `Document`. Без
    изоляции файлы копятся в проде-бакете вечно (`docs/checklist-novyy-modul.md` §9,
    найдено в ИС: 2310 никогда не удалявшихся объектов на момент
    обнаружения). Изоляция — отдельный бакет `test-<uuid>` на весь прогон pytest, не
    пофайловый учёт: бакет проще удалить целиком, чем отслеживать, что именно создал
    каждый тест, и заодно два параллельных прогона (два CI-джоба) не видят файлы друг
    друга.

    Lifecycle-правило на сутки — страховка от прогона, прерванного до teardown
    (Ctrl+C, OOM-килл, `pytest --timeout`): такой бакет не остаётся в MinIO навсегда,
    просто на сутки дольше, чем должен был бы.

    `AWS_STORAGE_BUCKET_NAME` — не часть `STORAGES` (`config/settings/base.py`), и
    Django's `setting_changed`-приёмник для сброса кэша хранилища
    (`django.test.signals.storages_changed`) слушает только смену самого `STORAGES`, не
    `AWS_STORAGE_BUCKET_NAME` — сброс `storages._storages`/`default_storage._wrapped`
    ниже сделан вручную, тем же приёмом, а не понадеявшись на сигнал, который сюда не
    доходит.
    """

    if not settings.AWS_S3_ENDPOINT_URL:
        # Реальный (не MinIO) эндпоинт — не создаём и не удаляем боевые бакеты втихую.
        yield
        return

    bucket_name = f"test-{uuid.uuid4()}"
    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )
    client.create_bucket(Bucket=bucket_name)
    client.put_bucket_lifecycle_configuration(
        Bucket=bucket_name,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-test-bucket",
                    "Status": "Enabled",
                    "Filter": {},
                    "Expiration": {"Days": 1},
                }
            ]
        },
    )

    settings.AWS_STORAGE_BUCKET_NAME = bucket_name
    # Тот же сброс кэша, что `django.test.signals.storages_changed` делает для смены
    # самого STORAGES — здесь вручную, см. докстринг выше.
    storages._storages = {}  # type: ignore[attr-defined]
    default_storage._wrapped = empty  # type: ignore[attr-defined]

    yield

    _empty_bucket(client, bucket_name)
    client.delete_bucket(Bucket=bucket_name)
