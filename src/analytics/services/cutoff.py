"""Закрытие и переоткрытие недельной отсечки (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.8; прототип `cutBtn`).

Закрытие фиксирует живую неделю участков (`selectors.live_rows`) снимком; отработанные
часы — из табеля, начальник производства может поправить их при закрытии (диалог
прототипа: «подставлены из табеля»). Переоткрытие удаляет снимок и пишет причину
в журнал. Права проверяет API (`rules.can_close_cutoff`), сервис — правила недели.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.analytics import calculations as calc
from src.analytics import selectors
from src.analytics.exceptions import (
    CutoffAlreadyClosed,
    CutoffNotClosed,
    FutureWeek,
    InvalidWorkedHours,
    NotMonday,
    ReasonRequired,
)
from src.analytics.models import CutoffAction, WeeklyCutoff, WeeklyCutoffEvent, WeeklyCutoffRow


def _check_week(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise NotMonday
    if week_start > calc.week_start(selectors.today()):
        raise FutureWeek


def close_week(
    week_start: date,
    *,
    actor_employee_id: UUID,
    comment: str = "",
    worked_hours: Mapping[UUID, Decimal] | None = None,
    closed_at: datetime | None = None,
) -> WeeklyCutoff:
    """Снимок недели по всем участкам с часами. `worked_hours` — правка отработанных
    часов по участку поверх табеля; `closed_at` — для демо-данных задним числом."""

    _check_week(week_start)
    centers = selectors.production_centers()
    overrides = dict(worked_hours or {})
    known = {c.id for c in centers}
    if any(wc not in known or hours < 0 for wc, hours in overrides.items()):
        raise InvalidWorkedHours
    with transaction.atomic():
        # Повторное закрытие ловит эта проверка; два одновременных — уникальность
        # `week_start` в БД: второе получит IntegrityError и откатится целиком.
        if WeeklyCutoff.objects.filter(week_start=week_start).exists():
            raise CutoffAlreadyClosed
        data = selectors.live_week_data([week_start])
        worked = {**selectors.worked_by_center(week_start), **overrides}
        rows = selectors.live_rows(week_start, centers, data, worked)
        cutoff = WeeklyCutoff.objects.create(
            week_start=week_start,
            closed_by_id=actor_employee_id,
            closed_at=closed_at or timezone.now(),
            comment=comment.strip(),
        )
        WeeklyCutoffRow.objects.bulk_create(
            WeeklyCutoffRow(
                cutoff=cutoff,
                work_center_id=row.work_center_id,
                planned_hours=row.planned,
                earned_hours=row.earned,
                worked_hours=calc.hours2(row.worked or calc.ZERO),
                checked=row.checked,
                defects=row.defects,
            )
            for row in rows
            if row.work_center_id is not None
        )
        WeeklyCutoffEvent.objects.create(
            week_start=week_start,
            action=CutoffAction.CLOSE,
            actor_id=actor_employee_id,
            text=cutoff.comment,
        )
    return cutoff


def reopen_week(week_start: date, *, actor_employee_id: UUID, reason: str) -> None:
    """Снимок удаляется, причина остаётся в журнале: неделя снова считается живой."""

    reason = reason.strip()
    if not reason:
        raise ReasonRequired
    with transaction.atomic():
        cutoff = WeeklyCutoff.objects.select_for_update().filter(week_start=week_start).first()
        if cutoff is None:
            raise CutoffNotClosed
        cutoff.delete()
        WeeklyCutoffEvent.objects.create(
            week_start=week_start,
            action=CutoffAction.REOPEN,
            actor_id=actor_employee_id,
            text=reason,
        )
