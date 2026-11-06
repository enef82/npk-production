"""Ручной ввод показаний (§3.7). Единственное место транзакций для `MeterReading`.

Расход между двумя показаниями раскладывается поровну по получасовым интервалам
между ними (`source = manual`) — все отчёты читают интервалы, и ручная точка учёта
в них ничем не отличается от SCADA. Первое показание — точка отсчёта, расхода нет.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from src.energy.calculations import HALF_HOUR, is_half_hour, spread
from src.energy.exceptions import InvalidReading
from src.energy.models import Meter, MeterInterval, MeterReading, MeterSource
from src.energy.services.common import as_actor

# Не больше года между показаниями — иначе опечатка в дате размазала бы расход на
# десятки тысяч интервалов.
MAX_GAP_SLOTS = 366 * 48


def record_reading(
    meter_id: UUID, taken_at: datetime, value: Decimal, *, actor_id: UUID | None
) -> MeterReading:
    if not is_half_hour(taken_at):
        raise InvalidReading("Время показания должно быть кратно 30 минутам.")
    if value < 0:
        raise InvalidReading("Показание не может быть отрицательным.")
    with transaction.atomic(), as_actor(actor_id):
        meter = Meter.objects.select_for_update().get(id=meter_id)
        previous = MeterReading.objects.filter(meter=meter).order_by("-taken_at").first()
        if previous is not None:
            if taken_at <= previous.taken_at:
                raise InvalidReading("Показание должно быть позже последнего внесённого.")
            if value < previous.value:
                raise InvalidReading("Показание меньше предыдущего — счётчик накопительный.")
        reading = MeterReading.objects.create(meter=meter, taken_at=taken_at, value=value)
        if previous is not None:
            slots = int((taken_at - previous.taken_at) / HALF_HOUR)
            if slots > MAX_GAP_SLOTS:
                raise InvalidReading("Между показаниями больше года — проверьте дату.")
            values = spread(value - previous.value, slots)
            MeterInterval.objects.bulk_create(
                [
                    MeterInterval(
                        meter=meter,
                        start=previous.taken_at + HALF_HOUR * index,
                        value=part,
                        source=MeterSource.MANUAL,
                    )
                    for index, part in enumerate(values)
                ],
                update_conflicts=True,
                unique_fields=["meter", "start"],
                update_fields=["value", "source"],
            )
    return reading
