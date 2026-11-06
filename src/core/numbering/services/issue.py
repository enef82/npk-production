"""Атомарная выдача номера — устойчивая к конкуренции (SELECT FOR UPDATE).

Обоснование SELECT FOR UPDATE вместо последовательности PostgreSQL —
`docs/adr/0009-numerator-select-for-update-ne-sequence.md`.

Блокировка строки `Numerator` сериализует все параллельные запросы по этому `code` до
коммита транзакции — поэтому последующий `get_or_create` на `NumeratorCounter` безопасен
даже ровно на границе периода: первый вызов в новом периоде создаёт строку счётчика,
уже не конкурируя ни с кем.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from src.core.numbering.models import Numerator, NumeratorCounter, NumeratorResetPeriod


def _period_key(numerator: Numerator, when: date) -> str:
    if numerator.reset_period == NumeratorResetPeriod.YEARLY:
        return str(when.year)
    if numerator.reset_period == NumeratorResetPeriod.MONTHLY:
        return f"{when.year}-{when.month:02d}"
    return ""


def _render(numerator: Numerator, when: date, seq: int) -> str:
    return numerator.template.format(year=when.year, month=when.month, seq=seq)


def issue_number(code: str, *, when: date | None = None) -> str:
    when = when or timezone.localdate()

    with transaction.atomic():
        numerator = Numerator.objects.select_for_update().get(code=code, is_active=True)
        period_key = _period_key(numerator, when)

        counter, _ = NumeratorCounter.objects.select_for_update().get_or_create(
            numerator=numerator,
            period_key=period_key,
            defaults={"last_value": 0},
        )
        counter.last_value += 1
        counter.save(update_fields=["last_value", "updated_at"])

        return _render(numerator, when, counter.last_value)
