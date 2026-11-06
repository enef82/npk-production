"""Критерий приёмки: нечёткий поиск по short_name использует GIN-индекс gin_trgm_ops."""

import pytest
from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from faker import Faker

from src.core.identity.models import Party, PartyStatus, PartyType
from src.core.identity.services.dedup import find_party_duplicates

ROW_COUNT = 10_000
INDEX_NAME = "core_identity_party_name_trgm"


@pytest.mark.django_db
def test_нечёткий_поиск_использует_индекс() -> None:
    # Названия должны быть реалистично разнообразны: если все строки — вариации одного
    # префикса («Компания 1», «Компания 2», ...), триграммы почти всех строк пересекаются
    # с запросом, и GIN-индекс перестаёт что-либо отсеивать. Faker с названиями компаний
    # воспроизводит боевые данные.
    fake = Faker("ru_RU")
    Faker.seed(2026)
    rows = [
        Party(
            inn=f"77{i:08d}",
            kpp="",
            legal_name=f"ООО «{fake.company()}»",
            short_name=fake.company(),
            party_type=PartyType.LEGAL,
            status=PartyStatus.ACTIVE,
        )
        for i in range(ROW_COUNT)
    ]
    Party.objects.bulk_create(rows, batch_size=1000)
    цель = rows[ROW_COUNT // 2].short_name

    with connection.cursor() as cursor:
        cursor.execute("ANALYZE core_identity_party")
        # pg_trgm.similarity_threshold — от него зависит, использует ли планировщик
        # GIN-индекс для оператора `%` (это то же самое, что делает find_party_duplicates).
        cursor.execute("SELECT set_limit(%s)", [0.4])
        # На 10 000 строках стоимость Seq Scan и Bitmap Index Scan у планировщика близки,
        # и выбор между ними шатается от прогона к прогону из-за случайной выборки ANALYZE
        # (см. отчёт: при большем количестве строк тот же индекс используется стабильно).
        # enable_seqscan=off — стандартный приём проверить, что план с индексом вообще
        # существует и работает, не завязываясь на конкретные cost-константы планировщика.
        cursor.execute("SET LOCAL enable_seqscan = off")

    qs = (
        Party.objects.exclude(status=PartyStatus.ARCHIVED)
        .filter(short_name__trigram_similar=цель)
        .annotate(similarity=TrigramSimilarity("short_name", цель))
        .order_by("-similarity")[:10]
    )
    plan = qs.explain(analyze=True)
    print(f"\n--- EXPLAIN ANALYZE, {ROW_COUNT} строк, запрос {цель!r} ---\n{plan}\n")

    assert INDEX_NAME in plan

    # Тот же путь целиком, как его использует сервис дедупликации (без enable_seqscan=off).
    найдено = find_party_duplicates(name=цель)
    assert найдено
