"""Демо-данные аналитики — закрытые отсечки за 8 прошлых недель (`seedCuts` и
`genHistory` прототипа, `docs/spec/00-prilozhenie-proizvodstvo.md` §3.8).

Строка отсечки = живая неделя участка + архивная история прототипа: демо-заказы
начались недавно, и без истории прошлые недели были бы пустыми. Архив — как
`genHistory`: план `мощность × U(0,55…0,85)` за вычетом плана демо-заказов, освоено
`план × U(0,78…1,06)`; отработано — `мощность × U(0,82…0,96)`, как `seedCuts`.
Закрывает Морозов Д.В. (начальник производства) в пятницу недели в 18:00.

Случайные величины — генератором Парка — Миллера с зерном прототипа: повторный посев
даёт ту же картину. Идемпотентно: уже закрытая неделя пропускается.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from src.analytics import calculations as calc
from src.analytics import selectors
from src.analytics.models import CutoffAction, WeeklyCutoff, WeeklyCutoffEvent, WeeklyCutoffRow
from src.core.org.models import Employee

DEMO_WEEKS = 8
CLOSED_BY = "0000120"  # Морозов Д.В., начальник производства
_CLOSE_TIME = time(18, 0)


class _Random:
    """Генератор Парка — Миллера прототипа (`rnd`): `seed × 16807 mod (2³¹ − 1)`.
    Возвращает `Decimal` в [0, 1) — без `float` (И6). Копия генератора `quality`:
    чужие `services` импортировать нельзя (И1), а в ядро демо-генератор не просится."""

    _MOD = 2147483647

    def __init__(self, seed: int = 11) -> None:
        self._state = seed

    def next(self) -> Decimal:
        self._state = (self._state * 16807) % self._MOD
        return Decimal(self._state - 1) / Decimal(self._MOD - 1)

    def uniform(self, low: str, high: str) -> Decimal:
        lo, hi = Decimal(low), Decimal(high)
        return lo + (hi - lo) * self.next()


def seed_demo(today: date | None = None) -> int:
    """Возвращает число созданных отсечек."""

    today = today or timezone.localdate()
    closer = Employee.objects.filter(personnel_number=CLOSED_BY).first()
    if closer is None:
        return 0
    current = calc.week_start(today)
    weeks = [current - timedelta(weeks=k) for k in range(DEMO_WEEKS, 0, -1)]
    existing = set(
        WeeklyCutoff.objects.filter(week_start__in=weeks).values_list("week_start", flat=True)
    )
    centers = selectors.production_centers()
    data = selectors.live_week_data(weeks)
    rnd = _Random()
    created = 0
    with transaction.atomic():
        for week in weeks:
            # Генератор крутится и для пропущенных недель: картина остальных не зависит
            # от того, какие недели уже закрыты.
            draws = [
                (
                    rnd.uniform("0.55", "0.85"),
                    rnd.uniform("0.78", "1.06"),
                    rnd.uniform("0.82", "0.96"),
                )
                for _ in centers
            ]
            if week in existing:
                continue
            live = selectors.live_rows(week, centers, data, worked=None)
            closed_at = timezone.make_aware(datetime.combine(week + timedelta(days=4), _CLOSE_TIME))
            cutoff = WeeklyCutoff.objects.create(
                week_start=week, closed_by=closer, closed_at=closed_at, comment=""
            )
            rows = []
            for center, row, (plan_k, earn_k, work_k) in zip(centers, live, draws, strict=True):
                capacity = Decimal(center.capacity) * calc.HOURS_PER_WEEK
                archive = max(calc.ZERO, capacity * plan_k - row.planned)
                rows.append(
                    WeeklyCutoffRow(
                        cutoff=cutoff,
                        work_center_id=center.id,
                        planned_hours=calc.hours2(row.planned + archive),
                        earned_hours=calc.hours2(row.earned + archive * earn_k),
                        worked_hours=(capacity * work_k).quantize(Decimal(1), ROUND_HALF_UP),
                        checked=row.checked,
                        defects=row.defects,
                    )
                )
            WeeklyCutoffRow.objects.bulk_create(rows)
            event = WeeklyCutoffEvent.objects.create(
                week_start=week, action=CutoffAction.CLOSE, actor=closer, text=""
            )
            # `auto_now_add` ставит текущее время; журнал демо датирован моментом закрытия.
            WeeklyCutoffEvent.objects.filter(id=event.id).update(created_at=closed_at)
            created += 1
    return created
