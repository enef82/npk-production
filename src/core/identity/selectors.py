"""Запросы на чтение и агрегаты модуля «Ядро: идентичность»."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.core.identity import registry
from src.core.identity.models import Item, Party, PartyStatus


def get_party(party_id: UUID) -> Party | None:
    return Party.objects.filter(id=party_id).first()


@dataclass(frozen=True)
class PartyBrief:
    id: UUID
    short_name: str
    inn: str
    status: PartyStatus


def get_parties_brief(ids: Iterable[UUID]) -> dict[UUID, PartyBrief]:
    """Пакетное чтение контрагентов по списку id — один запрос, без N+1.

    Первый потребитель — реестр заявок `crm` (`crm.api.routers.list_inquiries` поверх
    `crm.selectors.inquiries_queryset`): `Inquiry.customer_id` голый UUID без FK (И2),
    обычный `select_related` невозможен, а без наименования заказчика реестр заявок
    нечитаем. Читается пакетно уже по странице пагинации. Только четыре поля:
    `short_name` для отображения,
    `inn` — различить одноимённых контрагентов, `status` — пометить заявку
    архивированного заказчика (реакция на `identity.party_archived`, см.
    спецификация CRM ИС (IS_ERP, 10-crm) §5, подключается будущим шагом).
    """

    parties = Party.objects.filter(id__in=list(ids)).only("id", "short_name", "inn", "status")
    return {
        party.id: PartyBrief(
            id=party.id,
            short_name=party.short_name,
            inn=party.inn,
            status=PartyStatus(party.status),
        )
        for party in parties
    }


def get_item(item_id: UUID) -> Item | None:
    return Item.objects.filter(id=item_id).first()


def get_party_360(party_id: UUID) -> dict[str, dict[str, Any]]:
    """Собирает атрибуты всех зарегистрированных профилей контрагента.

    Обходит реестр модулей (`registry.iter_party_profiles`), не импортируя ни один
    функциональный модуль напрямую — модули регистрируют свои профили сами
    через `AppConfig.ready()`.
    """

    result: dict[str, dict[str, Any]] = {}
    for registration in registry.iter_party_profiles():
        profile = registration.model.objects.filter(  # type: ignore[attr-defined]
            party_id=party_id
        ).first()
        if profile is None:
            continue
        result[registration.model._meta.app_label] = {
            "title": registration.title,
            "attributes": profile.attributes,
        }
    return result
