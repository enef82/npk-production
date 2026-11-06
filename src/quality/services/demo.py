"""Демо-данные ОТК — перенос `QCP`, `qcSeed` и `genHistory` прототипа
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3, §3.8).

- 9 точек контроля прототипа с видами дефектов — по кодам участков `production`
  (`production.facade.list_work_centers`); миграцией их не засеять: участки заводит
  `production.seed_demo`.
- Записи контроля по операциям демо-заказов в работе (`qcSeed`): выполненная операция —
  запись в день окончания, идущая на 50 % и больше (кроме финального ОТК) — вчера.
- История брака за 12 прошлых недель (`genHistory`) — по операциям заказа на валы
  приводные (З-0393): у записи контроля обязана быть операция, а архив прототипа
  её не имел.

Случайные величины прототипа — детерминированным генератором Парка — Миллера с тем же
зерном (`rnd` прототипа): повторный посев даёт ту же картину. Записи журнала заказа
демо-записям не пишутся: фасад `production` ставит журналу текущее время, а демо-запись
датирована задним числом.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import floor
from typing import TypeVar
from uuid import UUID, uuid5

from django.db import transaction
from django.utils import timezone

from src.core.org.models import Employee
from src.production import facade as production
from src.quality.models import DefectCause, DefectType, InspectionPoint, InspectionRecord
from src.sales import facade as sales

# Тот же namespace, что в `production.services.demo` и `sales.services.demo`: заказ
# демо-набора находится по номеру заявки без чтения чужих моделей.
DEMO_NAMESPACE = UUID("5f0c3a52-7d4e-5b8a-9e61-2c4b1d7a9f30")
HISTORY_ORDER = "З-0393"
HISTORY_WEEKS = 12

# (код участка, точка контроля, финальный, виды дефектов) — `QCP` прототипа.
POINTS = (
    (
        "snab",
        "Входной контроль",
        False,
        ("несоответствие спецификации", "повреждение при доставке", "нет сертификата"),
    ),
    (
        "list",
        "Контроль геометрии (размеры, углы гибки)",
        False,
        ("угол гибки вне допуска", "размер вне допуска", "заусенцы, кромка"),
    ),
    (
        "meh",
        "Контроль допусков (размеры, шероховатость)",
        False,
        ("размер вне допуска", "шероховатость", "биение, соосность"),
    ),
    ("svar", "ВИК сварных швов", False, ("непровар", "поры", "подрез", "коробление")),
    (
        "pok",
        "Контроль покрытия (толщина, адгезия)",
        False,
        ("толщина покрытия", "адгезия", "потёки, включения"),
    ),
    ("sb", "Контроль сборки шкафа", False, ("некомплект", "ошибка сборки", "повреждение")),
    (
        "em",
        "Прозвонка и проверка монтажа",
        False,
        ("ошибка монтажа", "маркировка", "момент затяжки"),
    ),
    ("izg", "Контроль сборки узлов", False, ("люфт, зазор", "ошибка сборки", "некомплект")),
    (
        "otk",
        "Приёмо-сдаточные испытания",
        True,
        ("функциональный отказ", "несоответствие КД", "дефект внешнего вида"),
    ),
)

# Доля брака по участку (`QRATE`) и объём проверок в неделю (`QVOL`), прототип.
RATE = {
    "snab": Decimal("0.015"),
    "list": Decimal("0.04"),
    "meh": Decimal("0.05"),
    "svar": Decimal("0.035"),
    "pok": Decimal("0.06"),
    "sb": Decimal("0.02"),
    "em": Decimal("0.03"),
    "izg": Decimal("0.03"),
    "otk": Decimal("0.05"),
}
VOLUME = {
    "snab": (60, 150),
    "list": (80, 160),
    "meh": (120, 220),
    "svar": (30, 60),
    "pok": (40, 90),
    "sb": (6, 14),
    "em": (6, 14),
    "izg": (4, 10),
    "otk": (10, 20),
}
# Веса причин (`CAUSE_W`) — порядок справочника миграции `0002_seed_defect_causes`.
CAUSE_WEIGHTS = (
    ("Оператор", 30),
    ("Оборудование", 20),
    ("Материал / комплектующие", 15),
    ("КД / УП ЧПУ", 20),
    ("Технология", 10),
    ("Прочее", 5),
)
INSPECTOR = "0000130"  # Орлова Н.В., инженер ОТК
SUPPLY_INSPECTOR = "0000204"  # Кузнецов В., снабженец — входной контроль

_T = TypeVar("_T")


class _Random:
    """Генератор Парка — Миллера прототипа (`rnd`): `seed × 16807 mod (2³¹ − 1)`.
    Возвращает `Decimal` в [0, 1) — без `float` (И6)."""

    _MOD = 2147483647

    def __init__(self, seed: int = 11) -> None:
        self._state = seed

    def next(self) -> Decimal:
        self._state = (self._state * 16807) % self._MOD
        return Decimal(self._state - 1) / Decimal(self._MOD - 1)

    def uniform(self, low: Decimal, high: Decimal) -> Decimal:
        return low + (high - low) * self.next()

    def choice(self, items: Sequence[_T]) -> _T:
        return items[floor(self.next() * len(items))]

    def weighted(self, items: Sequence[tuple[_T, int]]) -> _T:
        r = self.next() * sum(weight for _, weight in items)
        for item, weight in items:
            r -= weight
            if r < 0:
                return item
        return items[0][0]


def _seed_points(centers: dict[str, UUID]) -> dict[UUID, InspectionPoint]:
    points = {}
    for code, name, is_final, defects in POINTS:
        if code not in centers:
            continue
        point, _ = InspectionPoint.objects.get_or_create(
            work_center_id=centers[code], defaults={"name": name, "is_final": is_final}
        )
        for order, defect in enumerate(defects, start=1):
            DefectType.objects.get_or_create(
                inspection_point=point, name=defect, defaults={"order": order}
            )
        points[point.work_center_id] = point
    return points


class _Seeder:
    def __init__(
        self,
        points: dict[UUID, InspectionPoint],
        codes: dict[UUID, str],
        people: dict[str, Employee],
    ) -> None:
        self.rnd = _Random()
        self.points = points
        self.codes = codes
        self.people = people
        self.defect_types = {
            point.id: list(point.defect_types.order_by("order")) for point in points.values()
        }
        causes = {cause.name: cause for cause in DefectCause.objects.all()}
        self.cause_weights = [(causes[name], weight) for name, weight in CAUSE_WEIGHTS]
        self.records: list[InspectionRecord] = []

    def _count(self, n: int, probability: Decimal) -> int:
        return sum(1 for _ in range(n) if self.rnd.next() < probability)

    def add(
        self,
        operation: production.OperationBrief,
        day: date,
        checked: int,
        rework: int,
        scrap: int,
        comment: str = "",
    ) -> None:
        point = self.points[operation.work_center_id]
        defects = rework + scrap
        code = self.codes[operation.work_center_id]
        inspector = self.people[
            SUPPLY_INSPECTOR if code == "snab" and not point.is_final else INSPECTOR
        ]
        self.records.append(
            InspectionRecord(
                operation_id=operation.id,
                order_id=operation.order_id,
                work_center_id=operation.work_center_id,
                date=day,
                inspector=inspector,
                checked=checked,
                rework=rework,
                scrap=scrap,
                defect_type=self.rnd.choice(self.defect_types[point.id]) if defects else None,
                cause=self.rnd.weighted(self.cause_weights) if defects else None,
                comment=comment,
            )
        )

    def operation_record(
        self, operation: production.OperationBrief, quantity: Decimal, materials: int, day: date
    ) -> None:
        """`qcSeed` прототипа."""

        code = self.codes[operation.work_center_id]
        half = int((quantity / 2).to_integral_value(ROUND_HALF_UP))
        checked = max(1, materials * max(1, half) if code == "snab" else int(quantity))
        defects = self._count(checked, RATE[code] * Decimal("1.6"))
        scrap = self._count(defects, Decimal("0.3"))
        self.add(
            operation,
            day,
            checked,
            defects - scrap,
            scrap,
            "Выявлено на контроле, передано на доработку" if defects else "",
        )

    def history_week(self, operation: production.OperationBrief, week: date, k: int) -> None:
        """`genHistory` прототипа для одной недели и участка. Архив прототипа держал
        проверки и брак отдельными строками (брак — с нулём проверенных); здесь
        каждая строка брака проверяет ровно свои дефектные штуки, а «годная» строка —
        остальное: сумма проверенных та же, ограничение «брак ≤ проверено» соблюдено."""

        code = self.codes[operation.work_center_id]
        point = self.points[operation.work_center_id]
        low, high = VOLUME[code]
        checked = int(self.rnd.uniform(Decimal(low), Decimal(high)).to_integral_value())
        trend = Decimal("0.7") + Decimal(k) * Decimal("0.06")
        final_factor = (
            min(Decimal("2.2"), Decimal("0.6") + Decimal(k) * Decimal("0.15"))
            if point.is_final
            else Decimal(1)
        )
        probability = (
            RATE[code] * trend * self.rnd.uniform(Decimal("0.6"), Decimal("1.4")) * final_factor
        )
        defects = self._count(checked, probability)
        day = week + timedelta(days=2)
        self.add(operation, day, checked - defects, 0, 0)
        while defects > 0:
            batch = min(defects, 1 + floor(self.rnd.next() * 3))
            defects -= batch
            scrap = self._count(batch, Decimal("0.4") if code == "meh" else Decimal("0.25"))
            self.add(operation, day, batch, batch - scrap, scrap, "Архив ОТК")


def _people() -> dict[str, Employee]:
    return {
        e.personnel_number: e
        for e in Employee.objects.filter(personnel_number__in=(INSPECTOR, SUPPLY_INSPECTOR))
    }


def seed_demo() -> None:
    today = timezone.localdate()
    centers = {center.code: center.id for center in production.list_work_centers()}
    people = _people()
    with transaction.atomic():
        points = _seed_points(centers)
        if InspectionRecord.objects.exists() or len(people) < 2:
            return
        seeder = _Seeder(points, {wc_id: code for code, wc_id in centers.items()}, people)
        yesterday = today - timedelta(days=1)
        history_operations: list[production.OperationBrief] = []
        history_order = uuid5(DEMO_NAMESPACE, f"order/{HISTORY_ORDER}")
        for order in sorted(production.list_active_orders(), key=lambda o: o.number):
            materials = len(sales.get_calc_materials(order.inquiry_id)) if order.inquiry_id else 1
            operations = production.list_order_operations(order.id)
            for op in operations:
                if op.work_center_id not in points:
                    continue
                if op.status == production.OperationStatus.DONE and op.planned_finish is not None:
                    seeder.operation_record(op, order.quantity, materials, op.planned_finish)
                elif (
                    op.status == production.OperationStatus.WORK
                    and op.progress >= 50
                    and not points[op.work_center_id].is_final
                ):
                    seeder.operation_record(op, order.quantity, materials, yesterday)
            if order.id == history_order:
                history_operations = operations
        _seed_history(seeder, history_operations, points, today)
        InspectionRecord.objects.bulk_create(seeder.records)


def _seed_history(
    seeder: _Seeder,
    operations: list[production.OperationBrief],
    points: dict[UUID, InspectionPoint],
    today: date,
) -> None:
    # На участок — одна операция заказа, самая трудоёмкая (на мехобработке — фрезерная).
    by_center: dict[UUID, production.OperationBrief] = {}
    for op in operations:
        if op.work_center_id in points:
            current = by_center.get(op.work_center_id)
            if current is None or op.hours > current.hours:
                by_center[op.work_center_id] = op
    current_week = today - timedelta(days=today.weekday())
    for k in range(1, HISTORY_WEEKS + 1):
        week = current_week - timedelta(weeks=k)
        for op in by_center.values():
            seeder.history_week(op, week, k)
