"""Реестр профилей модулей, заполняемый через `AppConfig.ready()`.

Ядру запрещено импортировать функциональные модули (инвариант И1), поэтому
профили регистрируют себя сами при старте приложения:

    # src/procurement/apps.py
    class ProcurementConfig(AppConfig):
        def ready(self) -> None:
            from src.core.identity.registry import register_party_profile
            from .models import VendorProfile
            register_party_profile(VendorProfile, title="Закупки")

`get_party_360` (см. `selectors.py`) обходит реестр и собирает все существующие
профили, не зная заранее, какие модули их зарегистрировали.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.identity.profiles import ItemProfile, PartyProfile


@dataclass(frozen=True)
class PartyProfileRegistration:
    model: type[PartyProfile]
    title: str


@dataclass(frozen=True)
class ItemProfileRegistration:
    model: type[ItemProfile]
    title: str


_party_profiles: list[PartyProfileRegistration] = []
_item_profiles: list[ItemProfileRegistration] = []


def register_party_profile(model: type[PartyProfile], *, title: str) -> None:
    _party_profiles.append(PartyProfileRegistration(model=model, title=title))


def register_item_profile(model: type[ItemProfile], *, title: str) -> None:
    _item_profiles.append(ItemProfileRegistration(model=model, title=title))


def iter_party_profiles() -> list[PartyProfileRegistration]:
    return list(_party_profiles)


def iter_item_profiles() -> list[ItemProfileRegistration]:
    return list(_item_profiles)
