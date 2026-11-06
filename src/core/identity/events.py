"""События, которые публикует модуль «Ядро: идентичность». Каталог — `docs/events.md`."""

from __future__ import annotations

import dataclasses
from typing import ClassVar

from src.core.events.base import DomainEvent


@dataclasses.dataclass(frozen=True)
class PartyArchived(DomainEvent):
    event_type: ClassVar[str] = "identity.party_archived"
