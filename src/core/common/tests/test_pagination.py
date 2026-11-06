import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext

from src.core.common.pagination import count_capped, decode_cursor, paginate_cursor

# `core.common` — нижний слой контракта `core-layers` (`.importlinter`), ему нельзя
# импортировать `core.identity` даже в тестах — поэтому пагинация проверяется на
# `ContentType`, а не на прикладной модели вроде `Party`: фреймворковая модель без
# слоевых зависимостей, всегда доступна и уже заполнена строками для всех моделей проекта.

ORDERING = ("app_label", "model", "pk")
ORDERING_KEY = "app_label"


@pytest.mark.django_db
def test_курсор_обходит_все_страницы_подряд_без_пропусков_и_дублей() -> None:
    total = ContentType.objects.count()
    assert total >= 3, "нужно хотя бы несколько ContentType в тестовой БД"

    seen: list[int] = []
    cursor = None
    for _ in range(total + 5):  # с запасом, реальных страниц меньше
        page, cursor = paginate_cursor(
            ContentType.objects.all(),
            ordering=ORDERING,
            ordering_key=ORDERING_KEY,
            cursor=cursor,
            page_size=2,
        )
        seen.extend(ct.pk for ct in page)
        if cursor is None:
            break

    assert len(seen) == total
    assert len(seen) == len(set(seen))
    assert seen == list(ContentType.objects.order_by(*ORDERING).values_list("pk", flat=True))


@pytest.mark.django_db
def test_вставка_записи_между_страницами_не_теряет_и_не_дублирует_исходные() -> None:
    """Ровно то различие с offset-пагинацией, ради которого затевалась курсорная:
    вставка строки между запросами страниц не должна ни задвоить, ни пропустить уже
    существовавшие строки. Синтетический префикс `app_label`, а не реальные модели —
    чтобы точно контролировать, куда по алфавиту попадёт новая запись.

    - вставка "перед курсором" (в уже пройденную часть) — не всплывает и не дублирует
      ничего из уже отданного (курсор её просто не увидит, это ожидаемо);
    - вставка "после курсора" (в ещё не пройденную часть) — обязана дойти до клиента
      в одной из следующих страниц, а не потеряться.
    """

    base = [ContentType.objects.create(app_label=f"zzz_seek_{i}", model="m") for i in range(5)]
    original_ids = {ct.pk for ct in base}
    qs = ContentType.objects.filter(app_label__startswith="zzz_seek_")

    page1, cursor = paginate_cursor(
        qs, ordering=("app_label", "pk"), ordering_key="app_label", cursor=None, page_size=2
    )
    assert [ct.app_label for ct in page1] == ["zzz_seek_0", "zzz_seek_1"]
    assert cursor is not None

    # "перед курсором": сортируется раньше zzz_seek_1, но позже уже отданного zzz_seek_0.
    behind_cursor = ContentType.objects.create(app_label="zzz_seek_0b", model="m")
    # "после курсора": сортируется позже всего, что ещё не отдавалось.
    ahead_of_cursor = ContentType.objects.create(app_label="zzz_seek_9", model="m")

    seen: list[int] = [ct.pk for ct in page1]
    for _ in range(10):
        page, cursor = paginate_cursor(
            qs, ordering=("app_label", "pk"), ordering_key="app_label", cursor=cursor, page_size=2
        )
        seen.extend(ct.pk for ct in page)
        if cursor is None:
            break

    assert len(seen) == len(set(seen))  # ни одна запись не задвоилась
    assert original_ids <= set(seen)  # ни одна исходная запись не потерялась
    assert ahead_of_cursor.pk in seen  # вставленная в ещё не пройденную часть — дошла
    assert behind_cursor.pk not in seen  # вставленная позади курсора — вне этого обхода, не баг


@pytest.mark.django_db
def test_смена_ключа_сортировки_сбрасывает_курсор_на_первую_страницу() -> None:
    _, cursor = paginate_cursor(
        ContentType.objects.all(),
        ordering=ORDERING,
        ordering_key="app_label",
        cursor=None,
        page_size=1,
    )

    other_ordering = ("-pk",)
    page, _ = paginate_cursor(
        ContentType.objects.all(),
        ordering=other_ordering,
        ordering_key="-pk",
        cursor=cursor,
        page_size=1,
    )

    expected_first = ContentType.objects.order_by(*other_ordering).first()
    assert expected_first is not None
    assert page[0].pk == expected_first.pk


@pytest.mark.django_db
def test_невалидный_курсор_не_роняет_запрос() -> None:
    page, next_cursor = paginate_cursor(
        ContentType.objects.all(),
        ordering=ORDERING,
        ordering_key=ORDERING_KEY,
        cursor="не-base64!!!",
        page_size=1000,
    )

    assert len(page) == ContentType.objects.count()
    assert next_cursor is None


def test_decode_cursor_возвращает_none_для_мусора() -> None:
    assert decode_cursor("not-valid-base64", "app_label") is None
    assert decode_cursor(None, "app_label") is None


@pytest.mark.django_db
def test_count_capped_точен_при_количестве_меньше_порога() -> None:
    for i in range(5):
        ContentType.objects.create(app_label=f"zzz_count_a_{i}", model="m")
    qs = ContentType.objects.filter(app_label__startswith="zzz_count_a_")

    assert count_capped(qs, cap=10) == 5


@pytest.mark.django_db
def test_count_capped_возвращает_none_при_количестве_больше_порога() -> None:
    for i in range(5):
        ContentType.objects.create(app_label=f"zzz_count_b_{i}", model="m")
    qs = ContentType.objects.filter(app_label__startswith="zzz_count_b_")

    assert count_capped(qs, cap=3) is None


@pytest.mark.django_db
def test_count_capped_ровно_на_границе_порога_не_none() -> None:
    """cap+1-я строка — это уже «больше порога», а не «на пороге»: cap строк ровно
    помещаются, count_capped обязан вернуть точное число, не None."""

    for i in range(3):
        ContentType.objects.create(app_label=f"zzz_count_c_{i}", model="m")
    qs = ContentType.objects.filter(app_label__startswith="zzz_count_c_")

    assert count_capped(qs, cap=3) == 3


@pytest.mark.django_db
def test_подзапрос_подсчёта_ограничен_limit() -> None:
    """Защита от «упрощения» count_capped обратно в COUNT(*) без LIMIT — деградация
    была бы незаметна на маленькой тестовой БД и проявилась бы только на проде,
    на десятках тысяч строк."""

    ContentType.objects.create(app_label="zzz_count_limit_check", model="m")
    qs = ContentType.objects.all()

    with CaptureQueriesContext(connection) as ctx:
        count_capped(qs, cap=1000)

    assert len(ctx.captured_queries) == 1
    sql = ctx.captured_queries[0]["sql"]
    assert "LIMIT 1001" in sql, sql
