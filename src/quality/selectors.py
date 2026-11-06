"""Запросы на чтение и отчёты модуля «ОТК и качество» (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.3, «Отчёты»; прототип `qcAgg`, `allQc`, `renderQuality`).

Неделя — с понедельника (`date_trunc('week')` PostgreSQL). Агрегаты считаются в БД
одним запросом на отчёт, а не перебором записей.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db.models import Case, F, IntegerField, Q, QuerySet, Sum, Value, When
from django.db.models.functions import Coalesce, TruncWeek

from src.quality.models import DefectCause, InspectionPoint, InspectionRecord

_HUNDRED = Decimal(100)
_PCT = Decimal("0.1")


@dataclass(frozen=True)
class QcTotals:
    checked: int = 0
    rework: int = 0
    scrap: int = 0
    operator_defects: int = 0

    @property
    def defects(self) -> int:
        return self.rework + self.scrap

    @property
    def pct(self) -> Decimal:
        """Доля брака от проверенного, % с одним знаком."""

        return percent(self.defects, self.checked)


def percent(part: int, whole: int) -> Decimal:
    if not whole:
        return Decimal("0.0")
    return (Decimal(part) * _HUNDRED / Decimal(whole)).quantize(_PCT, ROUND_HALF_UP)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _defects_expr() -> F:
    return F("rework") + F("scrap")  # type: ignore[return-value]


def _totals_annotations() -> dict[str, Coalesce]:
    return {
        "t_checked": Coalesce(Sum("checked"), Value(0)),
        "t_rework": Coalesce(Sum("rework"), Value(0)),
        "t_scrap": Coalesce(Sum("scrap"), Value(0)),
        "t_operator": Coalesce(
            Sum(
                Case(
                    When(cause__is_operator_fault=True, then=_defects_expr()),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        ),
    }


def _totals(row: dict[str, int]) -> QcTotals:
    return QcTotals(
        checked=row["t_checked"],
        rework=row["t_rework"],
        scrap=row["t_scrap"],
        operator_defects=row["t_operator"],
    )


# --- Справочники ------------------------------------------------------------------


def list_points(*, active_only: bool = True) -> list[InspectionPoint]:
    points = InspectionPoint.objects.prefetch_related("defect_types")
    if active_only:
        points = points.filter(is_active=True)
    return list(points)


def get_point_for_work_center(work_center_id: UUID) -> InspectionPoint | None:
    return (
        InspectionPoint.objects.filter(work_center_id=work_center_id, is_active=True)
        .prefetch_related("defect_types")
        .first()
    )


def work_centers_with_points(work_center_ids: Iterable[UUID]) -> set[UUID]:
    return set(
        InspectionPoint.objects.filter(
            work_center_id__in=list(work_center_ids), is_active=True
        ).values_list("work_center_id", flat=True)
    )


def list_causes() -> list[DefectCause]:
    return list(DefectCause.objects.filter(is_active=True))


# --- Записи -----------------------------------------------------------------------


def _records() -> QuerySet[InspectionRecord]:
    return InspectionRecord.objects.select_related("inspector", "defect_type", "cause")


def has_inspection(operation_id: UUID) -> bool:
    return InspectionRecord.objects.filter(operation_id=operation_id).exists()


def get_record(record_id: UUID) -> InspectionRecord | None:
    return _records().filter(id=record_id).first()


def records_for_operation(operation_id: UUID) -> list[InspectionRecord]:
    return list(_records().filter(operation_id=operation_id))


@dataclass(frozen=True)
class RecordFilters:
    date_from: date | None = None
    date_to: date | None = None
    work_center_id: UUID | None = None
    order_id: UUID | None = None
    cause_id: UUID | None = None
    defects_only: bool = False
    limit: int = 200


def list_records(filters: RecordFilters) -> list[InspectionRecord]:
    records = _records()
    if filters.date_from is not None:
        records = records.filter(date__gte=filters.date_from)
    if filters.date_to is not None:
        records = records.filter(date__lte=filters.date_to)
    if filters.work_center_id is not None:
        records = records.filter(work_center_id=filters.work_center_id)
    if filters.order_id is not None:
        records = records.filter(order_id=filters.order_id)
    if filters.cause_id is not None:
        records = records.filter(cause_id=filters.cause_id)
    if filters.defects_only:
        records = records.filter(Q(rework__gt=0) | Q(scrap__gt=0))
    return list(records[: filters.limit])


# --- Агрегаты ---------------------------------------------------------------------


def qc_by_operation(operation_ids: Iterable[UUID]) -> dict[UUID, QcTotals]:
    rows = (
        InspectionRecord.objects.filter(operation_id__in=list(operation_ids))
        .values("operation_id")
        .annotate(**_totals_annotations())
    )
    return {row["operation_id"]: _totals(row) for row in rows}


def totals(date_from: date, date_to: date, *, final: bool | None = None) -> QcTotals:
    records = InspectionRecord.objects.filter(date__gte=date_from, date__lte=date_to)
    if final is not None:
        final_centers = InspectionPoint.objects.filter(is_final=True).values("work_center_id")
        records = (
            records.filter(work_center_id__in=final_centers)
            if final
            else records.exclude(work_center_id__in=final_centers)
        )
    return _totals(records.aggregate(**_totals_annotations()))


@dataclass(frozen=True)
class WeekRow:
    week_start: date
    work_center_id: UUID
    totals: QcTotals


def week_rows(date_from: date, date_to: date) -> list[WeekRow]:
    """Проверено, доработка, списание, брак по вине оператора — по неделе и участку."""

    rows = (
        InspectionRecord.objects.filter(date__gte=date_from, date__lte=date_to)
        .annotate(week=TruncWeek("date"))
        .values("week", "work_center_id")
        .annotate(**_totals_annotations())
        .order_by("week", "work_center_id")
    )
    return [
        WeekRow(
            week_start=_as_date(row["week"]),
            work_center_id=row["work_center_id"],
            totals=_totals(row),
        )
        for row in rows
    ]


def _as_date(value: date) -> date:
    # TruncWeek от DateField отдаёт date; на случай datetime — без времени.
    return value if type(value) is date else value.date()  # type: ignore[attr-defined]


@dataclass(frozen=True)
class ParetoRow:
    name: str
    defects: int
    cumulative_pct: Decimal


def _pareto(date_from: date, date_to: date, field: str, limit: int) -> list[ParetoRow]:
    rows = list(
        InspectionRecord.objects.filter(
            date__gte=date_from, date__lte=date_to, **{f"{field}__isnull": False}
        )
        .values(f"{field}__name")
        .annotate(defect_count=Sum(_defects_expr()))
        .filter(defect_count__gt=0)
        .order_by("-defect_count", f"{field}__name")
    )
    total = sum(row["defect_count"] for row in rows)
    result = []
    cumulative = 0
    for row in rows[:limit]:
        cumulative += row["defect_count"]
        result.append(
            ParetoRow(
                name=row[f"{field}__name"],
                defects=row["defect_count"],
                cumulative_pct=percent(cumulative, total),
            )
        )
    return result


def pareto_causes(date_from: date, date_to: date, limit: int = 8) -> list[ParetoRow]:
    return _pareto(date_from, date_to, "cause", limit)


def pareto_defect_types(date_from: date, date_to: date, limit: int = 8) -> list[ParetoRow]:
    return _pareto(date_from, date_to, "defect_type", limit)


def top_defect_by_work_center(date_from: date, date_to: date) -> dict[UUID, tuple[str, int]]:
    """Главный вид дефекта точки контроля за период: (название, штук)."""

    rows = (
        InspectionRecord.objects.filter(
            date__gte=date_from, date__lte=date_to, defect_type__isnull=False
        )
        .values("work_center_id", "defect_type__name")
        .annotate(defect_count=Sum(_defects_expr()))
        .order_by("work_center_id", "-defect_count", "defect_type__name")
    )
    top: dict[UUID, tuple[str, int]] = {}
    for row in rows:
        if row["work_center_id"] not in top and row["defect_count"]:
            top[row["work_center_id"]] = (row["defect_type__name"], row["defect_count"])
    return top


# --- Сводка экрана «Качество» -----------------------------------------------------


@dataclass(frozen=True)
class WorkCenterSummary:
    point: InspectionPoint
    totals: QcTotals
    top_defect: tuple[str, int] | None
    # Изменение доли брака второй половины периода к первой, п.п. (`tr` прототипа).
    trend: Decimal


@dataclass(frozen=True)
class WeekDynamics:
    week_start: date
    checked: int
    intermediate_defects: int
    final_defects: int
    pct: Decimal


def _sum(rows: Iterable[WeekRow]) -> QcTotals:
    checked = rework = scrap = operator = 0
    for row in rows:
        checked += row.totals.checked
        rework += row.totals.rework
        scrap += row.totals.scrap
        operator += row.totals.operator_defects
    return QcTotals(checked=checked, rework=rework, scrap=scrap, operator_defects=operator)


def summary_by_work_center(weeks: list[date]) -> list[WorkCenterSummary]:
    """По точкам контроля за недели `weeks` (понедельники по возрастанию)."""

    date_from, date_to = weeks[0], weeks[-1] + timedelta(days=6)
    rows = week_rows(date_from, date_to)
    middle = weeks[len(weeks) // 2]
    top = top_defect_by_work_center(date_from, date_to)
    result = []
    for point in list_points():
        own = [row for row in rows if row.work_center_id == point.work_center_id]
        first = _sum(row for row in own if row.week_start < middle)
        last = _sum(row for row in own if row.week_start >= middle)
        result.append(
            WorkCenterSummary(
                point=point,
                totals=_sum(own),
                top_defect=top.get(point.work_center_id),
                trend=last.pct - first.pct,
            )
        )
    return result


def dynamics(weeks: list[date]) -> list[WeekDynamics]:
    """Брак по неделям: где выявлен — на промежуточном или на финальном контроле."""

    final = {p.work_center_id for p in list_points(active_only=False) if p.is_final}
    rows = week_rows(weeks[0], weeks[-1] + timedelta(days=6))
    result = []
    for week in weeks:
        own = [row for row in rows if row.week_start == week]
        total = _sum(own)
        final_totals = _sum(row for row in own if row.work_center_id in final)
        result.append(
            WeekDynamics(
                week_start=week,
                checked=total.checked,
                intermediate_defects=total.defects - final_totals.defects,
                final_defects=final_totals.defects,
                pct=total.pct,
            )
        )
    return result


def last_weeks(today: date, count: int) -> list[date]:
    current = week_start(today)
    return [current - timedelta(weeks=count - 1 - i) for i in range(count)]
