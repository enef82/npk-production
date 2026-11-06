"""Эндпоинты django-ninja модуля «Ядро: идентичность».

Курсорная пагинация и сортировка — через `core.common.pagination` (не декоратор
`@paginate`, см. докстроку модуля: сортировка задаётся запросом, а не фиксируется
на этапе декоратора). Права — через `rules.py` этого модуля, не через
`core.accounts` (слоевой контракт, `.importlinter`, запрещает identity → accounts).
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from django.conf import settings
from django.db.models import QuerySet
from django.http import Http404, HttpRequest
from ninja import Query, Router
from ninja.errors import ValidationError

from src.core.common.exceptions import PermissionDenied
from src.core.common.pagination import CursorPage, count_capped, paginate_cursor
from src.core.identity import selectors
from src.core.identity.models import Item, ItemStatus, ItemType, Party, PartyStatus, PartyType
from src.core.identity.rules import can_create_party, can_force_create_party
from src.core.identity.services.dedup import find_party_duplicates
from src.core.identity.services.party import PartyCreateDTO, create_party

from .filters import ItemFilters, PartyFilters
from .schemas import (
    DuplicateMatchOut,
    ItemListItem,
    PartyIn,
    PartyListItem,
    PartyOut,
    PartyProfileOut,
)

router = Router(tags=["identity"])

PARTY_ORDERING: dict[str, tuple[str, ...]] = {
    "short_name": ("short_name", "pk"),
    "-short_name": ("-short_name", "-pk"),
    "created_at": ("created_at", "pk"),
    "-created_at": ("-created_at", "-pk"),
}
PARTY_DEFAULT_ORDERING = "-created_at"

ITEM_ORDERING: dict[str, tuple[str, ...]] = {
    "name": ("name", "pk"),
    "-name": ("-name", "-pk"),
    "code": ("code", "pk"),
    "-code": ("-code", "-pk"),
    "created_at": ("created_at", "pk"),
    "-created_at": ("-created_at", "-pk"),
}
ITEM_DEFAULT_ORDERING = "-created_at"


class _AuthenticatedUser(Protocol):
    id: UUID

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


class AuthenticatedHttpRequest(HttpRequest):
    """См. `src.core.documents.api.routers.AuthenticatedHttpRequest` — тот же приём,
    но здесь тип нельзя импортировать напрямую: identity лежит ниже accounts."""

    auth: _AuthenticatedUser


def _resolve_ordering(
    allowed: dict[str, tuple[str, ...]], default: str, requested: str | None
) -> str:
    key = requested or default
    if key not in allowed:
        raise ValidationError([{"ordering": f"Недопустимая сортировка: {key!r}."}])
    return key


def _add_total(
    payload: dict[str, object], queryset: QuerySet[Any], with_total: bool
) -> dict[str, object]:
    """Точный `total` — по явному запросу клиента (`with_total=1`), не на каждой
    странице: число не меняется, пока не сменился фильтр, а `count_capped` — не
    бесплатная операция. Без `with_total` оба поля отсутствуют в ответе (`CursorPage`
    объявлен с `exclude_unset=True` на этих операциях) — не `null`, а именно нет ключа,
    чтобы клиент не путал «не считали» с «посчитали и там пусто»."""

    if not with_total:
        return payload
    cap = settings.PAGINATION_TOTAL_CAP
    payload["total"] = count_capped(queryset, cap)
    payload["total_cap"] = cap
    return payload


def _to_party_list_item(party: Party) -> PartyListItem:
    return PartyListItem(
        id=party.id,
        short_name=party.short_name,
        inn=party.inn,
        party_type=PartyType(party.party_type),
        status=PartyStatus(party.status),
        created_at=party.created_at,
    )


def _to_party_out(party: Party) -> PartyOut:
    return PartyOut(
        **_to_party_list_item(party).model_dump(),
        legal_name=party.legal_name,
        kpp=party.kpp,
        updated_at=party.updated_at,
    )


@router.get(
    "/parties",
    response=CursorPage[PartyListItem],
    operation_id="listParties",
    exclude_unset=True,
)
def list_parties(
    request: HttpRequest,
    filters: PartyFilters = Query(...),
    cursor: str | None = None,
    page_size: int = 20,
    ordering: str | None = None,
    with_total: bool = False,
) -> dict[str, object]:
    key = _resolve_ordering(PARTY_ORDERING, PARTY_DEFAULT_ORDERING, ordering)
    qs = filters.filter(Party.objects.all())
    items, next_cursor = paginate_cursor(
        qs,
        ordering=PARTY_ORDERING[key],
        ordering_key=key,
        cursor=cursor,
        page_size=min(max(page_size, 1), 100),
    )
    payload: dict[str, object] = {
        "items": [_to_party_list_item(p) for p in items],
        "next_cursor": next_cursor,
    }
    return _add_total(payload, qs, with_total)


@router.get(
    "/parties/check-duplicates",
    response=list[DuplicateMatchOut],
    operation_id="checkPartyDuplicates",
)
def check_party_duplicates(
    request: HttpRequest, inn: str = "", name: str = ""
) -> list[DuplicateMatchOut]:
    matches = find_party_duplicates(inn=inn, name=name)
    return [
        DuplicateMatchOut(
            id=m.candidate.id,
            label=str(m.candidate),
            inn=getattr(m.candidate, "inn", ""),
            score=str(m.score),
            reason=m.reason,
        )
        for m in matches
    ]


@router.get("/parties/{party_id}", response=PartyOut, operation_id="getParty")
def get_party(request: HttpRequest, party_id: UUID) -> PartyOut:
    party = selectors.get_party(party_id)
    if party is None:
        raise Http404
    return _to_party_out(party)


@router.get(
    "/parties/{party_id}/profiles",
    response=dict[str, PartyProfileOut],
    operation_id="getPartyProfiles",
)
def get_party_profiles(request: HttpRequest, party_id: UUID) -> dict[str, PartyProfileOut]:
    if selectors.get_party(party_id) is None:
        raise Http404
    return {
        module: PartyProfileOut(title=data["title"], attributes=data["attributes"])
        for module, data in selectors.get_party_360(party_id).items()
    }


@router.post("/parties", response=PartyOut, operation_id="createParty")
def create_party_view(request: AuthenticatedHttpRequest, data: PartyIn) -> PartyOut:
    if not can_create_party(request.auth):
        raise PermissionDenied("Недостаточно прав для создания контрагента.")
    if data.force and not can_force_create_party(request.auth):
        raise PermissionDenied("Создание вопреки дубликатам доступно только администратору данных.")

    party = create_party(
        PartyCreateDTO(
            inn=data.inn,
            kpp=data.kpp,
            legal_name=data.legal_name,
            short_name=data.short_name,
            party_type=data.party_type,
        ),
        actor_id=request.auth.id,
        force=data.force,
    )
    return _to_party_out(party)


@router.get(
    "/items",
    response=CursorPage[ItemListItem],
    operation_id="listItems",
    exclude_unset=True,
)
def list_items(
    request: HttpRequest,
    filters: ItemFilters = Query(...),
    cursor: str | None = None,
    page_size: int = 20,
    ordering: str | None = None,
    with_total: bool = False,
) -> dict[str, object]:
    key = _resolve_ordering(ITEM_ORDERING, ITEM_DEFAULT_ORDERING, ordering)
    qs = filters.filter(Item.objects.select_related("base_uom"))
    items, next_cursor = paginate_cursor(
        qs,
        ordering=ITEM_ORDERING[key],
        ordering_key=key,
        cursor=cursor,
        page_size=min(max(page_size, 1), 100),
    )
    payload: dict[str, object] = {
        "items": [
            ItemListItem(
                id=i.id,
                code=i.code,
                name=i.name,
                item_type=ItemType(i.item_type),
                base_uom=i.base_uom.code,
                status=ItemStatus(i.status),
                created_at=i.created_at,
            )
            for i in items
        ],
        "next_cursor": next_cursor,
    }
    return _add_total(payload, qs, with_total)
