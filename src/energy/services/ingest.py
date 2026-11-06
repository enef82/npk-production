"""Приём получасовых интервалов от SCADA (§3.7, формат предложения «SCADA и
энергоучёт»): конверт `{schema_version, source_id, message_id, items: [...]}`.

Идемпотентность — по `message_id`: повторная доставка того же пакета возвращает итог
первой обработки и ничего не меняет (уникальный `ScadaMessage.message_id` — последняя
линия защиты от гонки двух доставок). Строки проверяются по одной: плохая строка
отклоняется с причиной, остальные принимаются. Интервал, уже пришедший раньше
(другим пакетом), перезаписывается — SCADA досылает исправления.

Значение — строкой (`"12.5"`): число JSON читается как float, а float для количеств
запрещён (И6) — такая строка отклоняется.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from src.energy.calculations import is_half_hour
from src.energy.exceptions import UnsupportedSchemaVersion
from src.energy.models import Meter, MeterInterval, MeterSource, ScadaMessage
from src.energy.services.common import as_actor

SUPPORTED_MAJOR_VERSION = "1"
ENERGY_INTERVAL = "energy_interval"


@dataclass(frozen=True)
class ScadaEnvelope:
    schema_version: str
    source_id: str
    message_id: str
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IngestResult:
    message_id: str
    duplicate: bool
    accepted: int
    rejected: int
    errors: list[dict[str, Any]]


def _result(message: ScadaMessage, *, duplicate: bool) -> IngestResult:
    return IngestResult(
        message_id=message.message_id,
        duplicate=duplicate,
        accepted=message.items_accepted,
        rejected=message.items_rejected,
        errors=list(message.errors),
    )


def _error(index: int, code: str, message: str) -> dict[str, Any]:
    return {"index": index, "code": code, "message": message}


def _parse(
    index: int, item: dict[str, Any], meters: dict[str, Meter]
) -> tuple[Meter, datetime, Decimal] | dict[str, Any]:
    if item.get("type") != ENERGY_INTERVAL:
        return _error(
            index, "unsupported_type", f"Тип строки не поддерживается: {item.get('type')!r}."
        )
    meter = meters.get(str(item.get("meter_code", "")))
    if meter is None:
        return _error(index, "unknown_meter", f"Счётчик {item.get('meter_code')!r} не найден.")
    raw_start = item.get("start")
    try:
        start = datetime.fromisoformat(raw_start) if isinstance(raw_start, str) else None
    except ValueError:
        start = None
    if start is None or start.tzinfo is None:
        return _error(index, "invalid_start", "Начало — дата и время ISO 8601 с часовым поясом.")
    if not is_half_hour(start):
        return _error(index, "start_not_aligned", "Начало интервала должно быть кратно 30 минутам.")
    raw_value = item.get("value")
    if not isinstance(raw_value, str):
        return _error(index, "invalid_value", "Значение передаётся строкой десятичного числа.")
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        return _error(index, "invalid_value", f"Не число: {raw_value!r}.")
    if not value.is_finite() or value < 0:
        return _error(index, "invalid_value", "Расход — неотрицательное конечное число.")
    if value != value.quantize(Decimal("0.0001")) or value >= Decimal("1e12"):
        return _error(index, "invalid_value", "Не больше 4 знаков после запятой и 12 до.")
    return meter, start, value


def ingest_intervals(envelope: ScadaEnvelope, *, actor_id: UUID | None) -> IngestResult:
    if envelope.schema_version.split(".")[0] != SUPPORTED_MAJOR_VERSION:
        raise UnsupportedSchemaVersion(
            f"Версия формата {envelope.schema_version!r} не поддерживается "
            f"(ожидается {SUPPORTED_MAJOR_VERSION}.x)."
        )
    existing = ScadaMessage.objects.filter(message_id=envelope.message_id).first()
    if existing is not None:
        return _result(existing, duplicate=True)

    codes = {str(item.get("meter_code", "")) for item in envelope.items}
    meters = {meter.code: meter for meter in Meter.objects.filter(code__in=codes)}
    errors: list[dict[str, Any]] = []
    # (meter_id, start) → строка; повтор той же пары в пакете — побеждает последняя.
    accepted: dict[tuple[UUID, datetime], tuple[int, MeterInterval]] = {}
    for index, item in enumerate(envelope.items):
        parsed = _parse(index, item if isinstance(item, dict) else {}, meters)
        if isinstance(parsed, dict):
            errors.append(parsed)
            continue
        meter, start, value = parsed
        key = (meter.id, start)
        if key in accepted:
            errors.append(
                _error(accepted[key][0], "duplicate_in_message", "Интервал повторён ниже в пакете.")
            )
        accepted[key] = (
            index,
            MeterInterval(meter=meter, start=start, value=value, source=MeterSource.SCADA),
        )
    errors.sort(key=lambda error: int(error["index"]))

    try:
        with transaction.atomic(), as_actor(actor_id):
            message = ScadaMessage.objects.create(
                message_id=envelope.message_id,
                source_id=envelope.source_id,
                schema_version=envelope.schema_version,
                items_total=len(envelope.items),
                items_accepted=len(accepted),
                items_rejected=len(errors),
                errors=errors,
            )
            MeterInterval.objects.bulk_create(
                [interval for _, interval in accepted.values()],
                update_conflicts=True,
                unique_fields=["meter", "start"],
                update_fields=["value", "source"],
            )
    except IntegrityError:
        # Тот же пакет параллельно принят другой доставкой — отдаём её итог.
        concurrent = ScadaMessage.objects.filter(message_id=envelope.message_id).first()
        if concurrent is None:
            raise
        return _result(concurrent, duplicate=True)
    return _result(message, duplicate=False)
