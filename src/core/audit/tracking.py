"""Обёртка над `pghistory.track()` с дефолтами проекта.

Задание называет это «миксином» — у pghistory нет варианта через наследование, только
декоратор прямо на модели. Используется он вместо миксина; создаваемая Event-модель по
умолчанию живёт в том же приложении, что и отслеживаемая модель (свои миграции у
`core.identity`, `core.org` и т.д., а не у `core.audit`) — поэтому `core.audit` не
становится Django-приложением, ему нечего мигрировать.

`pghistory` — БД-триггеры (`django-pgtrigger`): ловят `INSERT`/`UPDATE`/`DELETE` любым
путём, включая `QuerySet.update()`/`bulk_update()` и прямой SQL — то, что сигнал-based
аудит пропускает (см. `tests/test_audit.py::test_pghistory_ловит_bulk_update`).
`pghistory.middleware.HistoryMiddleware` (см. `MIDDLEWARE`) прикрепляет пользователя
текущего запроса к каждой записи истории автоматически.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pghistory
from django.db import models

_ModelT = TypeVar("_ModelT", bound=type[models.Model])


def track(*, exclude: list[str] | None = None) -> Callable[[_ModelT], _ModelT]:
    decorator: Callable[[_ModelT], _ModelT] = pghistory.track(
        pghistory.InsertEvent(),
        pghistory.UpdateEvent(),
        pghistory.DeleteEvent(),
        exclude=exclude,
    )
    return decorator
