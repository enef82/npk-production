"""Поиск дубликатов контрагентов и номенклатуры: точное совпадение, затем нечёткое по триграммам."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection

from src.core.common.exceptions import ConflictError
from src.core.identity.models import Item, ItemStatus, Party, PartyStatus

DEFAULT_DEDUP_THRESHOLD = 0.4
FUZZY_LIMIT = 10


@dataclass(frozen=True)
class DuplicateMatch:
    """Кандидат в дубликаты: сущность, оценка схожести и причина совпадения."""

    candidate: Party | Item
    score: Decimal
    reason: str


class DuplicatesFound(ConflictError):
    code = "duplicates_found"
    default_message = "Найдены вероятные дубликаты."

    def __init__(self, matches: list[DuplicateMatch]) -> None:
        self.matches = matches
        details = [
            {
                "id": str(match.candidate.id),
                "label": str(match.candidate),
                "inn": getattr(match.candidate, "inn", ""),
                "score": str(match.score),
                "reason": match.reason,
            }
            for match in matches
        ]
        super().__init__(self.default_message, details=details)


def _resolve_threshold(threshold: float | None) -> float:
    if threshold is not None:
        return threshold
    return float(getattr(settings, "IDENTITY_DEDUP_THRESHOLD", DEFAULT_DEDUP_THRESHOLD))


def _set_similarity_threshold(threshold: float) -> None:
    """Задаёт pg_trgm.similarity_threshold для сессии — только так `%` использует GIN-индекс."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_limit(%s)", [threshold])


def find_party_duplicates(
    inn: str = "",
    kpp: str = "",
    name: str = "",
    threshold: float | None = None,
) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    matched_ids: set[object] = set()

    if inn:
        exact_qs = Party.objects.filter(inn=inn, kpp=kpp).exclude(status=PartyStatus.ARCHIVED)
        for party in exact_qs:
            matches.append(DuplicateMatch(candidate=party, score=Decimal("1"), reason="ИНН"))
            matched_ids.add(party.id)

    if name:
        _set_similarity_threshold(_resolve_threshold(threshold))
        fuzzy_qs = (
            Party.objects.exclude(status=PartyStatus.ARCHIVED)
            .exclude(id__in=matched_ids)
            .filter(short_name__trigram_similar=name)
            .annotate(similarity=TrigramSimilarity("short_name", name))
            .order_by("-similarity")[:FUZZY_LIMIT]
        )
        for party in fuzzy_qs:
            score = Decimal(str(round(party.similarity, 4)))
            matches.append(DuplicateMatch(candidate=party, score=score, reason="название"))

    return matches


def find_item_duplicates(
    code: str = "",
    name: str = "",
    threshold: float | None = None,
) -> list[DuplicateMatch]:
    matches: list[DuplicateMatch] = []
    matched_ids: set[object] = set()

    if code:
        exact_qs = Item.objects.filter(code__iexact=code).exclude(status=ItemStatus.ARCHIVED)
        for item in exact_qs:
            matches.append(DuplicateMatch(candidate=item, score=Decimal("1"), reason="код"))
            matched_ids.add(item.id)

    if name:
        _set_similarity_threshold(_resolve_threshold(threshold))
        fuzzy_qs = (
            Item.objects.exclude(status=ItemStatus.ARCHIVED)
            .exclude(id__in=matched_ids)
            .filter(name__trigram_similar=name)
            .annotate(similarity=TrigramSimilarity("name", name))
            .order_by("-similarity")[:FUZZY_LIMIT]
        )
        for item in fuzzy_qs:
            score = Decimal(str(round(item.similarity, 4)))
            matches.append(DuplicateMatch(candidate=item, score=score, reason="название"))

    return matches
