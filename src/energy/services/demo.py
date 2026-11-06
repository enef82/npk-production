"""Демо-данные модуля «Энергоучёт» — копия набора прототипа (`ERES`, `MPWR`, `METERS`,
`seedEnergy`, `profile`): 20 счётчиков деревом, тарифы, получасовые интервалы за
последние 30 суток.

Расход станков считается от их наработки (`equipment.facade.get_runtime`) и
номинальной мощности прототипа, расход узлов и вводов — сумма дочерних плюс
неучтённое (у ввода — 1–2,5 % потерь и аномалия «потребитель мимо учёта» в двое суток).
Генератор детерминированный: «случайные» числа — хеш ключа (`hsh` прототипа).
Идемпотентен: если счётчики уже есть, ничего не делает. Вызывать после
`equipment.facade.seed_demo()` — иначе станки без наработки дадут только холостой ход.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.energy.calculations import HALF_HOUR, SLOTS_PER_DAY, ZERO, day_start, q4
from src.energy.models import (
    EnergyResource,
    Meter,
    MeterInterval,
    MeterKind,
    MeterReading,
    MeterSource,
)
from src.energy.services.meter import MeterDTO, create_meter
from src.energy.services.resource import set_tariff
from src.equipment import facade as equipment

HISTORY_DAYS = 30
# Тарифы прототипа, ₽ за единицу. Сжатый воздух прототип считает по электроэнергии
# компрессора (7,9 × 0,115 кВт·ч на м³) — здесь это просто его тариф.
TARIFFS = {
    "el": Decimal("7.9"),
    "gas": Decimal("8.4"),
    "air": Decimal("0.9085"),
    "n2": Decimal("45"),
    "heat": Decimal("2650"),
    "water": Decimal("62"),
}
# Номинальная мощность, кВт: (под нагрузкой, холостой ход, выключен) — `MPWR`.
POWER = {
    "ИН-0012": (Decimal("28"), Decimal("4"), Decimal("0.6")),
    "ИН-0013": (Decimal("11"), Decimal("2.5"), Decimal("0.3")),
    "ИН-0021": (Decimal("9"), Decimal("1.5"), Decimal("0.2")),
    "ИН-0022": (Decimal("14"), Decimal("2.5"), Decimal("0.4")),
    "ИН-0023": (Decimal("12"), Decimal("2.2"), Decimal("0.4")),
    "ИН-0024": (Decimal("2.5"), Decimal("0.3"), Decimal("0")),
    "ИН-0031": (Decimal("14"), Decimal("0.4"), Decimal("0")),
    "ИН-0032": (Decimal("14"), Decimal("0.4"), Decimal("0")),
    "ИН-0041": (Decimal("9"), Decimal("2"), Decimal("0.2")),
}
# (код, наименование, ресурс, код родителя, вид, инв. № оборудования, источник)
METERS: tuple[tuple[str, str, str, str | None, MeterKind, str | None, MeterSource], ...] = (
    (
        "СЧ-ЭЭ-ВВОД",
        "Ввод ТП-1 (коммерческий учёт)",
        "el",
        None,
        MeterKind.INPUT,
        None,
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-МЗУ",
        "Механозаготовительный участок",
        "el",
        "СЧ-ЭЭ-ВВОД",
        MeterKind.NODE,
        None,
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ЛАЗ",
        "Лазерный станок",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0012",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ГИБ",
        "Листогибочный пресс",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0013",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ТОК1",
        "Токарный 16А20Ф3",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0021",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ТОК2",
        "Токарный центр Fanuc",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0022",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ФР",
        "Фрезерный VMC-850",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0023",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ПИЛА",
        "Ленточная пила",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0024",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-СВ1",
        "Сварочный пост №1",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0031",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-СВ2",
        "Сварочный пост №2",
        "el",
        "СЧ-ЭЭ-МЗУ",
        MeterKind.EQUIPMENT,
        "ИН-0032",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-СМУ",
        "Сборочно-монтажный участок",
        "el",
        "СЧ-ЭЭ-ВВОД",
        MeterKind.SHOP,
        None,
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-ПОКР",
        "Покрасочная камера",
        "el",
        "СЧ-ЭЭ-ВВОД",
        MeterKind.EQUIPMENT,
        "ИН-0041",
        MeterSource.SCADA,
    ),
    (
        "СЧ-ЭЭ-КОМПР",
        "Компрессорная",
        "el",
        "СЧ-ЭЭ-ВВОД",
        MeterKind.COMPRESSOR,
        "ИН-0051",
        MeterSource.SCADA,
    ),
    ("СЧ-ЭЭ-АБК", "АБК и офис", "el", "СЧ-ЭЭ-ВВОД", MeterKind.OFFICE, None, MeterSource.MANUAL),
    ("СЧ-ГАЗ-ВВОД", "Газ, ввод", "gas", None, MeterKind.INPUT, None, MeterSource.SCADA),
    (
        "СЧ-ГАЗ-ПЕЧЬ",
        "Печь полимеризации",
        "gas",
        "СЧ-ГАЗ-ВВОД",
        MeterKind.EQUIPMENT,
        "ИН-0041",
        MeterSource.SCADA,
    ),
    ("РСХ-ВОЗД", "Выход компрессора", "air", None, MeterKind.OTHER, "ИН-0051", MeterSource.SCADA),
    ("РСХ-N2-ЛАЗ", "Азот на лазер", "n2", None, MeterKind.OTHER, "ИН-0012", MeterSource.SCADA),
    (
        "СЧ-ТЭ-ВВОД",
        "Тепловой ввод (отопление)",
        "heat",
        None,
        MeterKind.INPUT,
        None,
        MeterSource.MANUAL,
    ),
    ("СЧ-ВОДА", "Водопровод, ввод", "water", None, MeterKind.INPUT, None, MeterSource.MANUAL),
)
# Счётчики станков механозаготовительного участка: код → инв. № станка.
MZU_METERS = {spec[0]: spec[5] for spec in METERS if spec[3] == "СЧ-ЭЭ-МЗУ" and spec[5]}
ANOMALY_KWH = Decimal("185")
READING_BASE = Decimal("10000")

Profile = list[Decimal]
Runtime = dict[tuple[str, date], equipment.RuntimeRow]


def _noise(*parts: object) -> Decimal:
    """Детерминированное число в [0, 1) с 4 знаками — FNV-1a от ключа (`hsh`)."""

    value = 2166136261
    for char in "|".join(str(part) for part in parts):
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return Decimal(value % 10000) / Decimal(10000)


def _uniform(low: str, high: str, *key: object) -> Decimal:
    lo, hi = Decimal(low), Decimal(high)
    return lo + (hi - lo) * _noise(*key)


def _is_work_slot(slot: int, weekend: bool) -> bool:
    """Смена 8:00–17:00 без обеда 12:00–13:00 (`WORK` прототипа)."""

    return not weekend and 16 <= slot < 34 and not 24 <= slot < 26


def _shaped(active: Decimal, base_total: Decimal, weekend: bool, key: str) -> Profile:
    """Ровная база на все 48 получасов + активная часть по рабочим получасам с
    детерминированной неровностью (0,8…1,2), нормированной на сумму."""

    work = [s for s in range(SLOTS_PER_DAY) if _is_work_slot(s, weekend)]
    base = base_total / SLOTS_PER_DAY
    profile = [base] * SLOTS_PER_DAY
    if active <= 0:
        return profile
    if not work:
        return [base + active / SLOTS_PER_DAY] * SLOTS_PER_DAY
    weights = {s: Decimal("0.8") + Decimal("0.4") * _noise(key, s) for s in work}
    total_weight = sum(weights.values(), ZERO)
    for slot, weight in weights.items():
        profile[slot] += active * weight / total_weight
    return profile


def _background(total: Decimal, weekend: bool, key: str) -> Profile:
    """Цех и прочие: в выходной — ровно, в рабочий — 8 % база, остальное в смену."""

    base_total = total if weekend else total * Decimal("0.08")
    return _shaped(total - base_total, base_total, weekend, key)


def _sum(*profiles: Profile) -> Profile:
    return [sum(values, ZERO) for values in zip(*profiles, strict=True)]


def _node(children: list[Profile], extra: Decimal) -> Profile:
    """Узел: дочерние + неучтённое ровно по суткам (`profile` прототипа для input/node)."""

    total = _sum(*children) if children else [ZERO] * SLOTS_PER_DAY
    return [value + extra / SLOTS_PER_DAY for value in total]


def _day_profiles(day: date, back: int, runtime: Runtime, anomaly: set[date]) -> dict[str, Profile]:
    weekend = day.weekday() >= 5
    key = day.isoformat()
    p: dict[str, Profile] = {}

    def machine(inventory_no: str) -> Profile:
        loaded, idle_kw, off_kw = POWER[inventory_no]
        log = runtime.get((inventory_no, day))
        if log is None:
            return _shaped(ZERO, Decimal("24") * off_kw, weekend, inventory_no + key)
        run = (log.run * loaded + log.setup * idle_kw * Decimal("1.3")) * _uniform(
            "0.9", "1.08", inventory_no, key
        )
        idle = log.idle * idle_kw
        off = max(ZERO, (Decimal("24") - log.run - log.setup - log.idle - log.down) * off_kw)
        return _shaped(run, idle + off, weekend, inventory_no + key)

    for code, inventory_no in MZU_METERS.items():
        p[code] = machine(inventory_no)
    p["СЧ-ЭЭ-ПОКР"] = machine("ИН-0041")
    p["СЧ-ЭЭ-МЗУ"] = _node(
        [p[code] for code in MZU_METERS],
        Decimal("7.2") if weekend else Decimal("18"),  # 0,3×24 / 1,5×9 + 0,3×15
    )
    smu = (
        Decimal("19.2")
        if weekend
        else Decimal("162") * _uniform("0.8", "1.1", "smu", key) + Decimal("12")
    )
    p["СЧ-ЭЭ-СМУ"] = _background(smu, weekend, "smu" + key)
    load = ZERO if weekend else Decimal("74.25") * _uniform("0.85", "1.1", "cl", key)
    hold = Decimal("24" if weekend else "15") * Decimal("3.3") * _uniform("0.85", "1.1", "cn", key)
    p["СЧ-ЭЭ-КОМПР"] = _shaped(load, hold, weekend, "cmp" + key)
    office = (
        Decimal("36")
        if weekend
        else Decimal("54") * _uniform("0.85", "1.1", "abk", key) + Decimal("22.5")
    )
    p["СЧ-ЭЭ-АБК"] = _shaped(
        office - (office if weekend else Decimal("36")),
        office if weekend else Decimal("36"),
        weekend,
        "abk" + key,
    )
    children = [
        p[code] for code in ("СЧ-ЭЭ-МЗУ", "СЧ-ЭЭ-СМУ", "СЧ-ЭЭ-ПОКР", "СЧ-ЭЭ-КОМПР", "СЧ-ЭЭ-АБК")
    ]
    children_total = sum((sum(c, ZERO) for c in children), ZERO)
    losses = children_total * (_uniform("1.01", "1.025", "in", key) - 1)
    p["СЧ-ЭЭ-ВВОД"] = _node(children, losses + (ANOMALY_KWH if day in anomaly else ZERO))

    oven = runtime.get(("ИН-0041", day))
    gas_run = oven.run * Decimal("6.2") if oven else ZERO
    gas_idle = oven.idle * Decimal("1.1") if oven else ZERO
    p["СЧ-ГАЗ-ПЕЧЬ"] = _shaped(gas_run, gas_idle, weekend, "gas" + key)
    p["СЧ-ГАЗ-ВВОД"] = _node(
        [p["СЧ-ГАЗ-ПЕЧЬ"]],
        (gas_run + gas_idle) * Decimal("0.02") + (ZERO if weekend else Decimal("1.5")),
    )
    p["РСХ-ВОЗД"] = [value / Decimal("0.115") for value in p["СЧ-ЭЭ-КОМПР"]]
    laser = runtime.get(("ИН-0012", day))
    p["РСХ-N2-ЛАЗ"] = _shaped(
        laser.run * Decimal("5.5") if laser else ZERO, ZERO, weekend, "n2" + key
    )
    heat = Decimal("0.85") + Decimal("0.003") * back + _uniform("-0.08", "0.08", "heat", key)
    p["СЧ-ТЭ-ВВОД"] = _shaped(ZERO, heat, weekend, "heat" + key)
    water = _uniform("0.1", "0.3", "w", key) if weekend else _uniform("0.9", "1.5", "w", key)
    p["СЧ-ВОДА"] = _background(water, weekend, "water" + key)
    return p


def _anomaly_days(today: date) -> set[date]:
    """Двое рабочих суток подряд ~11 дней назад: ввод больше суммы дочерних на 185 кВт·ч."""

    day = today - timedelta(days=11)
    while day.weekday() >= 4:  # пятница тоже не годится: следующий день выходной
        day -= timedelta(days=1)
    return {day, day + timedelta(days=1)}


def seed_demo() -> None:
    if Meter.objects.exists():
        return
    today = timezone.localdate()
    date_from = today - timedelta(days=HISTORY_DAYS)
    by_inventory = {item.inventory_no: item.id for item in equipment.list_equipment()}
    inventory_by_id = {eid: inv for inv, eid in by_inventory.items()}
    runtime: Runtime = {
        (inventory_by_id[row.equipment_id], row.date): row
        for row in equipment.get_runtime(date_from, today - timedelta(days=1))
        if row.equipment_id in inventory_by_id
    }
    with transaction.atomic():
        resources = {r.code: r for r in EnergyResource.objects.all()}
        for code, tariff in TARIFFS.items():
            if code in resources:
                set_tariff(resources[code].id, today - timedelta(days=365), tariff, actor_id=None)
        meters = _create_meters(resources, by_inventory)
        _create_intervals(meters, today, runtime)


def _create_meters(
    resources: dict[str, EnergyResource], by_inventory: dict[str, UUID]
) -> dict[str, Meter]:
    meters: dict[str, Meter] = {}
    for order, (code, name, resource, parent, kind, inventory_no, source) in enumerate(METERS):
        if resource not in resources:
            continue
        meters[code] = create_meter(
            MeterDTO(
                code=code,
                name=name,
                resource_id=resources[resource].id,
                kind=kind,
                parent_id=meters[parent].id if parent else None,
                equipment_id=by_inventory.get(inventory_no) if inventory_no else None,
                source=source,
                order=order,
            ),
            actor_id=None,
        )
    return meters


def _create_intervals(meters: dict[str, Meter], today: date, runtime: Runtime) -> None:
    anomaly = _anomaly_days(today)
    intervals: list[MeterInterval] = []
    readings: list[MeterReading] = []
    cumulative = dict.fromkeys(meters, READING_BASE)
    for back in range(HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=back)
        start = day_start(day)
        profiles = _day_profiles(day, back, runtime, anomaly)
        for code, meter in meters.items():
            values = [q4(value) for value in profiles[code]]
            intervals.extend(
                MeterInterval(
                    meter=meter, start=start + HALF_HOUR * slot, value=value, source=meter.source
                )
                for slot, value in enumerate(values)
            )
            if meter.source == MeterSource.MANUAL:
                readings.append(MeterReading(meter=meter, taken_at=start, value=cumulative[code]))
                cumulative[code] += sum(values, ZERO)
    for code, meter in meters.items():
        if meter.source == MeterSource.MANUAL:
            readings.append(
                MeterReading(meter=meter, taken_at=day_start(today), value=cumulative[code])
            )
    MeterInterval.objects.bulk_create(intervals, batch_size=5000, ignore_conflicts=True)
    MeterReading.objects.bulk_create(readings, ignore_conflicts=True)
