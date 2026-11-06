"""Ограничения БД модуля «Аналитика»: попытка нарушить → `IntegrityError` (CLAUDE.md §8);
снимок отсечки не правится даже мимо сервиса (триггер)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError

from src.analytics.models import CutoffAction, WeeklyCutoff, WeeklyCutoffEvent, WeeklyCutoffRow
from src.analytics.tests.factories import WeeklyCutoffFactory, WeeklyCutoffRowFactory
from src.core.org.tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_неделя_отсечки_начинается_с_понедельника() -> None:
    with pytest.raises(IntegrityError, match="analytics_cutoff_week_starts_monday"):
        WeeklyCutoffFactory.create(week_start=date(2026, 10, 7))  # среда


def test_одну_неделю_нельзя_закрыть_дважды() -> None:
    WeeklyCutoffFactory.create(week_start=date(2026, 10, 5))
    with pytest.raises(IntegrityError, match="week_start"):
        WeeklyCutoffFactory.create(week_start=date(2026, 10, 5))


def test_участок_в_снимке_один_раз() -> None:
    row = WeeklyCutoffRowFactory.create()
    with pytest.raises(IntegrityError, match="analytics_cutoff_row_unique_wc"):
        WeeklyCutoffRowFactory.create(cutoff=row.cutoff, work_center_id=row.work_center_id)


def test_брака_в_снимке_не_больше_чем_проверено() -> None:
    with pytest.raises(IntegrityError, match="analytics_cutoff_row_defects_within_checked"):
        WeeklyCutoffRowFactory.create(checked=2, defects=3)


def test_план_и_отработанное_не_отрицательны() -> None:
    with pytest.raises(IntegrityError, match="analytics_cutoff_row_hours_non_negative"):
        WeeklyCutoffRowFactory.create(worked_hours=Decimal("-1"))


def test_отрицательное_освоение_в_снимке_допустимо() -> None:
    row = WeeklyCutoffRowFactory.create(earned_hours=Decimal("-2.50"))
    assert row.earned_hours == Decimal("-2.50")


def test_строку_снимка_нельзя_изменить_даже_мимо_сервиса() -> None:
    row = WeeklyCutoffRowFactory.create(earned_hours=Decimal("36"))
    with pytest.raises(IntegrityError, match="не изменяется"):
        WeeklyCutoffRow.objects.filter(id=row.id).update(earned_hours=Decimal("40"))


def test_шапку_снимка_нельзя_изменить() -> None:
    row = WeeklyCutoffRowFactory.create()
    cutoff = row.cutoff
    with pytest.raises(IntegrityError, match="не изменяется"):
        WeeklyCutoff.objects.filter(id=cutoff.id).update(comment="задним числом")


def test_переоткрытие_удаляет_снимок_со_строками() -> None:
    row = WeeklyCutoffRowFactory.create()
    row.cutoff.delete()
    assert not WeeklyCutoffRow.objects.exists()


def test_переоткрытие_в_журнале_только_с_причиной() -> None:
    with pytest.raises(IntegrityError, match="analytics_cutoff_event_reopen_has_reason"):
        WeeklyCutoffEvent.objects.create(
            week_start=date(2026, 10, 5),
            action=CutoffAction.REOPEN,
            actor=EmployeeFactory.create(),
            text="",
        )
