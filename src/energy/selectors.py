"""Запросы на чтение и отчёты модуля «Энергоучёт» (§3.7, прототип `renderEnergy`):
расход и стоимость по дням/месяцам и ресурсам, дерево счётчиков с балансами,
получасовой профиль суток, баланс узла, удельный расход оборудования.

Сутки — локальные (часовой пояс проекта). Агрегаты считает БД (группировка по
счётчику и суткам), стоимость — Python по тарифу на каждые сутки (`TariffTable`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.db.models import QuerySet, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from src.energy.calculations import (
    SLOTS_PER_DAY,
    ZERO,
    Balance,
    TariffTable,
    balance,
    day_start,
    q4,
    slot_of,
    specific_consumption,
)
from src.energy.models import (
    EnergyResource,
    Meter,
    MeterInterval,
    MeterKind,
    MeterReading,
    ScadaMessage,
    TariffPeriod,
)
from src.equipment import facade as equipment

# --- Справочники ------------------------------------------------------------------


def list_resources() -> QuerySet[EnergyResource]:
    return EnergyResource.objects.order_by("order", "name")


def get_resource_by_code(code: str) -> EnergyResource | None:
    return EnergyResource.objects.filter(code=code).first()


def list_tariff_periods(resource_ids: list[UUID] | None = None) -> QuerySet[TariffPeriod]:
    qs = TariffPeriod.objects.all()
    if resource_ids is not None:
        qs = qs.filter(resource_id__in=resource_ids)
    return qs.order_by("resource_id", "valid_from")


def tariff_tables(resources: list[EnergyResource]) -> dict[UUID, TariffTable]:
    periods: dict[UUID, list[TariffPeriod]] = defaultdict(list)
    for period in list_tariff_periods([r.id for r in resources]):
        periods[period.resource_id].append(period)
    return {
        r.id: TariffTable(
            starts=[p.valid_from for p in periods[r.id]],
            tariffs=[p.tariff for p in periods[r.id]],
            fallback=r.tariff,
        )
        for r in resources
    }


def list_meters(resource_id: UUID | None = None) -> QuerySet[Meter]:
    qs = Meter.objects.select_related("resource", "parent")
    if resource_id is not None:
        qs = qs.filter(resource_id=resource_id)
    return qs.order_by("resource__order", "order", "code")


def get_meter(meter_id: UUID) -> Meter | None:
    return list_meters().filter(id=meter_id).first()


def list_readings(meter_id: UUID, limit: int = 50) -> list[MeterReading]:
    return list(MeterReading.objects.filter(meter_id=meter_id).order_by("-taken_at")[:limit])


def list_scada_messages(limit: int = 20) -> list[ScadaMessage]:
    return list(ScadaMessage.objects.order_by("-created_at")[:limit])


# --- Агрегаты интервалов -------------------------------------------------------------


def _intervals(date_from: date, date_to: date) -> QuerySet[MeterInterval]:
    return MeterInterval.objects.filter(
        start__gte=day_start(date_from), start__lt=day_start(date_to + timedelta(days=1))
    )


def daily_by_meter(
    meter_ids: list[UUID], date_from: date, date_to: date
) -> dict[UUID, dict[date, Decimal]]:
    """Расход по счётчику и локальным суткам — одним групповым запросом."""

    rows = (
        _intervals(date_from, date_to)
        .filter(meter_id__in=meter_ids)
        .annotate(day=TruncDate("start", tzinfo=timezone.get_current_timezone()))
        .values("meter_id", "day")
        .annotate(total=Sum("value"))
        .values_list("meter_id", "day", "total")
    )
    result: dict[UUID, dict[date, Decimal]] = defaultdict(dict)
    for meter_id, day, total in rows:
        result[meter_id][day] = total
    return result


def totals_by_meter(meter_ids: list[UUID], date_from: date, date_to: date) -> dict[UUID, Decimal]:
    rows = (
        _intervals(date_from, date_to)
        .filter(meter_id__in=meter_ids)
        .values("meter_id")
        .annotate(total=Sum("value"))
        .values_list("meter_id", "total")
    )
    totals = dict.fromkeys(meter_ids, ZERO)
    totals.update(dict(rows))
    return totals


def _cost(by_day: dict[date, Decimal], table: TariffTable) -> Decimal:
    return q4(sum((value * table.on(day) for day, value in by_day.items()), ZERO))


# --- Расход и стоимость по ресурсам -------------------------------------------------


@dataclass(frozen=True)
class ConsumptionRow:
    resource: EnergyResource
    period: date  # сутки или первое число месяца
    quantity: Decimal
    cost: Decimal


def consumption(
    date_from: date, date_to: date, *, by_month: bool = False, resource_id: UUID | None = None
) -> list[ConsumptionRow]:
    """Расход ресурса = сумма его корневых счётчиков (вводов), как в прототипе."""

    resources = list(list_resources())
    if resource_id is not None:
        resources = [r for r in resources if r.id == resource_id]
    roots = list(Meter.objects.filter(resource__in=resources, parent__isnull=True))
    daily = daily_by_meter([m.id for m in roots], date_from, date_to)
    tables = tariff_tables(resources)
    per_resource: dict[UUID, dict[date, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for meter in roots:
        for day, value in daily.get(meter.id, {}).items():
            per_resource[meter.resource_id][day] += value
    rows: list[ConsumptionRow] = []
    for resource in resources:
        buckets: dict[date, dict[date, Decimal]] = defaultdict(dict)
        for day, value in per_resource[resource.id].items():
            key = day.replace(day=1) if by_month else day
            buckets[key][day] = value
        for period in sorted(buckets):
            by_day = buckets[period]
            rows.append(
                ConsumptionRow(
                    resource=resource,
                    period=period,
                    quantity=sum(by_day.values(), ZERO),
                    cost=_cost(by_day, tables[resource.id]),
                )
            )
    return rows


# --- Дерево счётчиков ---------------------------------------------------------------


@dataclass(frozen=True)
class MeterTreeRow:
    meter: Meter
    level: int
    quantity: Decimal
    previous_quantity: Decimal
    share_pct: Decimal | None
    cost: Decimal
    balance: Balance | None  # только у счётчика с дочерними


def meter_tree(resource: EnergyResource, date_from: date, date_to: date) -> list[MeterTreeRow]:
    """Счётчики ресурса деревом (обход в глубину) за период и такой же предыдущий:
    расход, доля от суммы вводов, стоимость, небаланс узла."""

    meters = list(list_meters(resource.id))
    ids = [m.id for m in meters]
    length = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length - 1)
    daily = daily_by_meter(ids, date_from, date_to)
    previous = totals_by_meter(ids, prev_from, prev_to)
    table = tariff_tables([resource])[resource.id]
    totals = {m.id: sum(daily.get(m.id, {}).values(), ZERO) for m in meters}
    children: dict[UUID | None, list[Meter]] = defaultdict(list)
    for meter in meters:
        children[meter.parent_id].append(meter)
    roots_total = sum((totals[m.id] for m in children[None]), ZERO)

    rows: list[MeterTreeRow] = []

    def walk(meter: Meter, level: int) -> None:
        kids = children.get(meter.id, [])
        value = totals[meter.id]
        rows.append(
            MeterTreeRow(
                meter=meter,
                level=level,
                quantity=value,
                previous_quantity=previous.get(meter.id, ZERO),
                share_pct=(value / roots_total * 100).quantize(Decimal("0.01"))
                if roots_total
                else None,
                cost=_cost(daily.get(meter.id, {}), table),
                balance=balance(value, sum((totals[k.id] for k in kids), ZERO)) if kids else None,
            )
        )
        for kid in kids:
            walk(kid, level + 1)

    for root in children[None]:
        walk(root, 0)
    return rows


@dataclass(frozen=True)
class DailyRow:
    meter_id: UUID
    day: date
    quantity: Decimal


def daily_series(resource: EnergyResource, date_from: date, date_to: date) -> list[DailyRow]:
    """«Расход по дням»: сутки × счётчик ресурса (стек по дочерним ввода строит фронт)."""

    ids = [m.id for m in list_meters(resource.id)]
    daily = daily_by_meter(ids, date_from, date_to)
    return [
        DailyRow(meter_id=meter_id, day=day, quantity=value)
        for meter_id in ids
        for day, value in sorted(daily.get(meter_id, {}).items())
    ]


# --- Профиль, баланс, удельный расход ------------------------------------------------


def day_profile(meter_id: UUID, day: date) -> list[Decimal]:
    """48 получасовых значений расхода за локальные сутки (пустой получас — ноль)."""

    values = [ZERO] * SLOTS_PER_DAY
    for start, value in (
        _intervals(day, day).filter(meter_id=meter_id).values_list("start", "value")
    ):
        values[slot_of(start)] += value
    return values


@dataclass(frozen=True)
class BalanceDay:
    day: date
    balance: Balance


@dataclass(frozen=True)
class NodeBalance:
    meter: Meter
    children: list[Meter]
    total: Balance
    days: list[BalanceDay]


def node_balance(meter: Meter, date_from: date, date_to: date) -> NodeBalance:
    """Баланс узла «ввод − Σ дочерних» = потери: за период и по суткам."""

    kids = list(Meter.objects.filter(parent=meter).order_by("order", "code"))
    daily = daily_by_meter([meter.id, *[k.id for k in kids]], date_from, date_to)
    days: list[BalanceDay] = []
    day = date_from
    while day <= date_to:
        own = daily.get(meter.id, {}).get(day, ZERO)
        children_sum = sum((daily.get(k.id, {}).get(day, ZERO) for k in kids), ZERO)
        days.append(BalanceDay(day, balance(own, children_sum)))
        day += timedelta(days=1)
    total = balance(
        sum((d.balance.input for d in days), ZERO), sum((d.balance.children for d in days), ZERO)
    )
    return NodeBalance(meter=meter, children=kids, total=total, days=days)


@dataclass(frozen=True)
class SpecificRow:
    meter: Meter
    equipment_id: UUID
    equipment_name: str
    inventory_no: str
    energy: Decimal
    machine_hours: Decimal
    specific: Decimal | None  # кВт·ч на машино-час
    cost: Decimal


def specific_consumption_report(date_from: date, date_to: date) -> list[SpecificRow]:
    """Удельный расход электроэнергии оборудования: кВт·ч счётчика станка на
    машино-час (работа + наладка) по наработке `equipment.facade.get_runtime`."""

    meters = [
        m
        for m in list_meters()
        if m.equipment_id is not None
        and m.resource.code == "el"
        and m.kind in (MeterKind.EQUIPMENT, MeterKind.COMPRESSOR)
    ]
    if not meters:
        return []
    daily = daily_by_meter([m.id for m in meters], date_from, date_to)
    table = tariff_tables([meters[0].resource])[meters[0].resource_id]
    hours: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for row in equipment.get_runtime(date_from, date_to):
        hours[row.equipment_id] += row.machine_hours
    names = {item.id: item for item in equipment.list_equipment()}
    rows = []
    for meter in meters:
        assert meter.equipment_id is not None
        energy = sum(daily.get(meter.id, {}).values(), ZERO)
        machine_hours = hours[meter.equipment_id]
        brief = names.get(meter.equipment_id)
        rows.append(
            SpecificRow(
                meter=meter,
                equipment_id=meter.equipment_id,
                equipment_name=brief.name if brief else "",
                inventory_no=brief.inventory_no if brief else "",
                energy=energy,
                machine_hours=machine_hours,
                specific=specific_consumption(energy, machine_hours),
                cost=_cost(daily.get(meter.id, {}), table),
            )
        )
    return rows
