"""Курсорная пагинация с сортировкой, задаваемой запросом.

Встроенный `ninja.pagination.CursorPagination` фиксирует `ordering` на этапе
декоратора — одна сортировка на весь эндпоинт, а сам пагинатор создаётся один раз
на процесс и переиспользуется между запросами. DataTable (шаг 10) требует сортировку
по клику на колонку; хранить текущую сортировку в атрибуте пагинатора небезопасно —
это общее изменяемое состояние, которое гонится между параллельными запросами
(тредовый `runserver`/ASGI). Поэтому здесь не подкласс `CursorPagination`, а набор
чистых функций без разделяемого состояния — вызываются явно из `api/routers.py`,
без декоратора `@paginate`.

Курсор — это seek-позиция (keyset pagination): значения полей сортировки последней
строки предыдущей страницы, закодированные в base64 вместе с ключом сортировки.
Смена сортировки делает старый курсор нерелевантным — при несовпадении ключа курсор
молча игнорируется (страница начинается заново), а не падает с ошибкой.

Только «вперёд»: возврата к предыдущей странице по курсору с backend не предусмотрено
намеренно — фронтенд ведёт свой стек посещённых курсоров (следующая страница добавляет
курсор в URL, кнопка «Назад» просто убирает последний). Это резко проще двунаправленной
курсорной арифметики и не требует состояния на сервере вообще.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from django.db.models import Model, Q, QuerySet
from ninja import Schema


class CursorPage[T](Schema):
    items: list[T]
    next_cursor: str | None = None
    # Оба поля отсутствуют в ответе, если клиент не запрашивал `with_total` — эндпоинт
    # ставится с `exclude_unset=True` (`api/routers.py`), а роутер кладёт эти ключи
    # в возвращаемый dict только когда total реально посчитан; Pydantic отличает
    # «поле не передано» от «поле передано как None» через `model_fields_set`,
    # `total=None` при заданном `total_cap` сериализуется как `null`, а не пропадает.
    total: int | None = None
    total_cap: int | None = None


def _split_ordering(ordering: tuple[str, ...]) -> list[tuple[str, bool]]:
    """`("-created_at", "pk")` → `[("created_at", True), ("pk", False)]` (поле, убывание)."""

    return [(f[1:], True) if f.startswith("-") else (f, False) for f in ordering]


def _position_of(item: Model, ordering: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(item, field) for field, _ in _split_ordering(ordering)}


def _seek_filter(ordering: tuple[str, ...], position: dict[str, Any]) -> Q:
    """Q-объект «первая строка после `position` в порядке `ordering`» (row-wise seek,
    разложенный в OR цепочки AND — Django не умеет сравнение кортежей напрямую)."""

    fields = _split_ordering(ordering)
    clauses = Q()
    equalities: dict[str, Any] = {}
    for field, desc in fields:
        clause = Q(**equalities) if equalities else Q()
        lookup = "lt" if desc else "gt"
        clause &= Q(**{f"{field}__{lookup}": position[field]})
        clauses |= clause
        equalities = {**equalities, field: position[field]}
    return clauses


def encode_cursor(position: dict[str, Any], ordering_key: str) -> str:
    payload = json.dumps({"o": ordering_key, "p": position}, default=str, ensure_ascii=False)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str | None, ordering_key: str) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("o") != ordering_key:
        return None
    position = payload.get("p")
    return position if isinstance(position, dict) else None


def paginate_cursor(
    queryset: QuerySet[Any],
    *,
    ordering: tuple[str, ...],
    ordering_key: str,
    cursor: str | None,
    page_size: int,
) -> tuple[list[Any], str | None]:
    queryset = queryset.order_by(*ordering)
    position = decode_cursor(cursor, ordering_key)
    if position is not None:
        queryset = queryset.filter(_seek_filter(ordering, position))

    items = list(queryset[: page_size + 1])
    has_next = len(items) > page_size
    items = items[:page_size]

    next_cursor = (
        encode_cursor(_position_of(items[-1], ordering), ordering_key) if has_next else None
    )
    return items, next_cursor


def count_capped(queryset: QuerySet[Any], cap: int) -> int | None:
    """`COUNT(*)`, ограниченный `cap` строками — не сканирует набор целиком, если он
    больше порога. `queryset[:cap + 1].count()` заставляет Django обернуть срез в
    подзапрос (`SELECT COUNT(*) FROM (... LIMIT cap+1) subquery`, проверено —
    `test_подзапрос_подсчёта_ограничен_limit`), а не считать весь набор и резать потом:
    досчитать честный COUNT(*) до конца таблицы на тысячах строк с фильтром — не то же
    самое, что прерваться на cap+1-й строке. `order_by()` снимает унаследованную
    сортировку — порядок строк подсчёту не нужен, а сортировка внутри LIMIT стоит
    времени впустую.

    Возвращает `None`, если строк больше `cap` (граница неизвестна, только «больше»)."""

    capped_count = queryset.order_by()[: cap + 1].count()
    return None if capped_count > cap else capped_count
